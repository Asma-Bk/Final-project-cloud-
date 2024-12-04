from fastapi import FastAPI, HTTPException, Request
import boto3
import httpx
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
    tusted_host_ip = get_instances_by_tag(ec2, "MySQL_CLUSTER", "Trusted_Host")
except Exception as e:
    print(f"Error while retrieving the Trusted Host instance IP: {e}")    
    
trusted_host_URL = f"http://{tusted_host_ip}/trustedhost"

VALID_API_KEYS = {"LOG8415E"} # Define the valid API keys
async def check_request(request: Request):
    # Extract the API key from the request headers
    api_key = request.headers.get("x-api-key")
    
    # Check if the API key is present and valid
    if not api_key:
        print("API key missing, the request will be blocked")
        raise HTTPException(status_code=401, detail="API key missing")
    if api_key not in VALID_API_KEYS:
        print("Invalid API key, the request will be blocked")
        raise HTTPException(status_code=403, detail="Invalid API key")
    # If the API key is valid, allow the request to proceed
    print("API key is valid, proceeding with the request")
    return True
        
@app.post("/database")
async def forward(request: Request):
    query_params = dict(request.query_params)
    request_id = query_params.get("request_id")  # Extract the request ID from query parameters
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # NOW
    print(f"[{timestamp}] [Request ID: {request_id}] The Gatekeeper received a request.")

     # Verify the request
    await check_request(request)
    # Forward the request to the trusted host and return the response
    try:
        async with httpx.AsyncClient() as client:
            # Forward the original request body and headers
            body = await request.body()
            response = await client.post(trusted_host_URL, params=query_params, content=body, headers=dict(request.headers))
        print(f"[{timestamp}] [Request ID: {request_id}] Successfully forwarded the request to the Trusted Host.")
        # Return the response from the proxy to the original client
        return response.json()
    except Exception as e:
        print(f"[{timestamp}] [Request ID: {request_id}] Error while forwarding the request to the Trusted Host: {e}")
        raise HTTPException(status_code=500, detail="Failed to forward the request to the Trusted Host")
if __name__ == "__main__":
    # TRUSTED_HOST_URL =""
    uvicorn.run(app, host="0.0.0.0", port=80)