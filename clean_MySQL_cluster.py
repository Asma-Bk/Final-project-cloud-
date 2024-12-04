from utils.aws_cleanup import cleanup
from utils.aws_setup import get_path
from utils.constants import *
import boto3, os
from dotenv import load_dotenv


load_dotenv()

aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_session_token = os.getenv('AWS_SESSION_TOKEN')

# Create EC2 client
ec2 = boto3.client('ec2',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    aws_session_token = aws_session_token,
    region_name = "us-east-1"
)

with open(get_path('configs/nat_gateway_id.txt'), 'r') as f:
      nat_gateway_id = f.read().strip()
with open(get_path('configs/private_subnet_id.txt'), 'r') as f:
      private_subnet_id = f.read().strip()
with open(get_path('configs/elastic_ip_aloc_id.txt'), 'r') as f:
      elastic_ip_alloc_id = f.read().split()
security_groups = [WORKERS_SG_NAME, PROXY_SG_NAME, TRUSTEDHOST_SG_NAME, GATEKEEPER_SG_NAME]         #Deletion is done in this order
cleanup(ec2,security_groups, nat_gateway_id, private_subnet_id, elastic_ip_alloc_id)
