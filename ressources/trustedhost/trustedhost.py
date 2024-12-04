from fastapi import FastAPI, HTTPException, Request
import httpx
import boto3
import uvicorn
from datetime import datetime

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
    proxy_ip = get_instances_by_tag(ec2, "MySQL_CLUSTER", "Proxy")
except Exception as e:
    print(f"Error while retrieving the Proxy instance IP: {e}")    
    
proxy_URL = f"http://{proxy_ip}/proxy"


@app.post("/trustedhost")
async def forward(request: Request):
    query_params = dict(request.query_params)
    request_id = query_params.get("request_id")  # Extract the request ID
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [Request ID: {request_id}] The Trusted Host received a request from the Gatekeeper.")
    try:
        async with httpx.AsyncClient() as client:
            # Forward the original request  to the Proxy
            body = await request.body()
            response = await client.post(proxy_URL, params=query_params, content=body, headers=dict(request.headers))
        print(f"[{timestamp}] [Request ID: {request_id}] Successfully forwarded the request to the Proxy.")
        # Return the response from the proxy to the original client
        return response.json()
    except Exception as e:
        print(f"[{timestamp}] [Request ID: {request_id}] Error while forwarding the request to the Proxy: {e}")
        raise HTTPException(status_code=500, detail="Failed to forward the request to the Proxy") 

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)
