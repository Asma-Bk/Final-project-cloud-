from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import random
import boto3
import uvicorn
from ping3 import ping
import pymysql
# from sshtunnel import SSHTunnelForwarder
from datetime import datetime
from decimal import Decimal

app = FastAPI()


def get_instances_by_tag(ec2,tag_key, tag_value):
    response = ec2.describe_instances(
        Filters=[
            {
                "Name": f"tag:{tag_key}",
                "Values": [tag_value]
            },{
            "Name": "instance-state-name",
            "Values": ["running"]
        }

        ]
    )

    if len(response["Reservations"]) == 0:
        return []
    instances = response['Reservations']
    if instances:
        first_instance = instances[0]['Instances'][0]
        private_ip = first_instance.get('PrivateIpAddress')
    return private_ip

# Connect to EC2
ec2 = boto3.client("ec2",
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    aws_session_token = aws_session_token,
    region_name = "us-east-1"
)


try:
    Manager_ip = get_instances_by_tag(ec2, "MySQL_CLUSTER", "Manager")
    Worker1_ip = get_instances_by_tag(ec2, "MySQL_CLUSTER", "Worker1")
    Worker2_ip = get_instances_by_tag(ec2, "MySQL_CLUSTER", "Worker2")
except Exception as e:
    print(f"Error while retrieving instance IPs: {e}")
    
@app.post("/proxy")
async def handle_request(request: Request):
    # Extract query parameters
    query_params = dict(request.query_params)
    strategy = query_params.get('strategy')
    request_id = query_params.get("request_id")  # Extract the request ID
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [Request ID: {request_id}] The Proxy received a request from the Trusted Host.")
    print("proceeding with strategy: ", strategy)
    # Extract the query from the request body
    query = await request.body()  # Read raw body
    query = query.decode('utf-8')  # Decode if needed

    if not strategy:
        raise HTTPException(status_code=400, detail="Strategy parameter is required")

    if strategy == "direct":
        node_ip = direct_hit()
    elif strategy == "random":
        node_ip = random_hit()
    elif strategy == "customized":
        node_ip = customized_hit()
    else:
        raise HTTPException(status_code=400, detail="Invalid strategy")


    # determine the type of the query
    query_lower = query.lower().strip()
    if query_lower.startswith("select"):
        query_type = "read"
    elif query_lower.startswith(("insert", "update", "delete", "create", "alter", "drop")):
        query_type = "write"
    else:
        raise HTTPException(status_code=400, detail="Unsupported query type")
    
    
    # Forward the query to the chosen IP based on its type and the strategy
    if query_type == "read":
        if strategy == "direct":
            print("Executing the read query on the master node...")
        else:
            print("Executing the read query on a worker node...")
        result = execute_query(node_ip, query)
    else:
        result = execute_query(Manager_ip, query)    
        # Replicate the write query to the worker nodes
        print("Replicating the query to the worker nodes...")
        print(execute_query(Worker1_ip, query, 1))
        print(execute_query(Worker2_ip, query, 2))
 
    return result
    
def direct_hit():
    # incoming requests to MySQL master node without logic to distribute the requests
    return Manager_ip

def random_hit():
    # randomly select a worker node to forward the request to
    n = random.choice([1,2])
    print(f"Worker{n} is randomly selected")
    if n == 1:

        return Worker1_ip
    else:
        return Worker2_ip


def customized_hit():
    # select the most responsive worker node to forward the request to
    worker1_ping = ping(Worker1_ip)
    worker2_ping = ping(Worker2_ip)
    print(f"Worker1 ping: {worker1_ping}")
    print(f"Worker2 ping: {worker2_ping}")
    if worker1_ping < worker2_ping:
        print("Worker1 is more responsive")
        return Worker1_ip
    else:
        print("Worker2 is more responsive")
        return Worker2_ip

    
def execute_query(node_ip, query, replicate=0):
    try:
        # Establish direct connection to the MySQL server
        conn = pymysql.connect(
            host=node_ip,  # Use the direct IP address of the MySQL server
            user='proxy_user',  # Replace with your MySQL username
            password='98486293',  # Replace with your MySQL password
            db='sakila',  # Replace with your database name
            port=3306,  # Default MySQL port
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True  # No need to call conn.commit() after each query
        )
        cursor = conn.cursor()
        
        # Execute the query
        cursor.execute(query)
        
        if replicate > 0:
            # Handle replication status message
            result = f"Data replicated successfully to worker node {replicate}"
        else:
            # Fetch results for read queries
            result = cursor.fetchall()
            for row in result:
                for key, value in row.items():
                    if isinstance(value, Decimal):
                        row[key] = float(value)  # Convert Decimal to float
                    elif isinstance(value, datetime):
                        row[key] = value.isoformat()  # Convert datetime to ISO format string
            print(result)
        
        # Close the connection
        conn.close()
        return result

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)
    