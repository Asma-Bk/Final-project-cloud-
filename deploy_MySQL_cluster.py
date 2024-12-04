import os
import time
import boto3
from dotenv import load_dotenv

from utils.aws_setup import *
from utils.constants import *
from ressources.proxy.bootstrap import get_proxy_user_data
from ressources.gatekeeper.bootstrap import get_gatekeeper_user_data
from ressources.trustedhost.bootstrap import get_trusted_host_user_data

#Retrieve the AWS credentials from the .env file
os.environ.pop('AWS_ACCESS_KEY_ID', None)
os.environ.pop('AWS_SECRET_ACCESS_KEY', None)
os.environ.pop('AWS_SESSION_TOKEN', None)

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

#Create key pair 
key_pair_path = generate_key_pair(ec2, KEY_PAIR_NAME)
# Create Security Groups
gatekeeper_rules = [
    {   
    "IpProtocol": "tcp",
    "FromPort": 80,
    "ToPort": 80,
    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Internet facing instance : Allow HTTP from outside"}],
    },
    {
    "IpProtocol": "tcp",
    "FromPort": 22,
    "ToPort": 22,
    "IpRanges": [{"CidrIp": '0.0.0.0/0', "Description": "Allow SSH for testing."}],
    },
]
gatekeeper_grp_id  = create_security_group(ec2,GATEKEEPER_SG_NAME, "Gatekeeper Security Group", gatekeeper_rules)

trustedhost_rules = [
    {
        "IpProtocol": "tcp",
        "FromPort": 80,
        "ToPort": 80,
        "UserIdGroupPairs": [
            {"GroupId": gatekeeper_grp_id, "Description": "Internal-facing instance: Allow HTTP only from Gatekeeper."}
        ]
    },
    {
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "UserIdGroupPairs": [
            {"GroupId": gatekeeper_grp_id, "Description": "Allow SSH from Gatekeeper only for testing."}
        ]
    }
]
trustedhost_grp_id = create_security_group(ec2, TRUSTEDHOST_SG_NAME, "Trusted Host Security Group", trustedhost_rules)

rules_proxy = [
    {
        "IpProtocol": "tcp",
        "FromPort": 80,
        "ToPort": 80,
        "UserIdGroupPairs": [
            {"GroupId": trustedhost_grp_id, "Description": "Allow HTTP only from Trusted Host."}
        ]
    },
    {
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "UserIdGroupPairs": [
            {"GroupId": gatekeeper_grp_id, "Description": "Allow SSH from Gatekeeper only for testing."}
        ]
    },
]
proxy_grp_id = create_security_group(ec2, PROXY_SG_NAME, "Proxy Security Group", rules_proxy)

rules_workers = [
    {
        "IpProtocol": "tcp",
        "FromPort": 3306,
        "ToPort": 3306,
        "UserIdGroupPairs": [
            {"GroupId": proxy_grp_id, "Description": "Allow MySQL connections only for the Proxy."}
        ]
    },
    {
        "IpProtocol": "icmp",
        "FromPort": -1,
        "ToPort": -1,
        "IpRanges": [{"CidrIp": "172.31.0.0/16", "Description": "Allow ping within the VPC."}]
    },
    {
        "IpProtocol": "tcp",
        "FromPort": 22,
        
        "ToPort": 22,
        "UserIdGroupPairs": [
            {"GroupId": gatekeeper_grp_id, "Description": "Allow SSH from Gatekeeper only for testing."}
        ]
    },
]
workers_grp_id = create_security_group(ec2, WORKERS_SG_NAME, "Workers Security Group", rules_workers)



###############Create a NAT Gateway###############
# Find a public subnet where the NAT Gateway will be placed
public_subnet_id = find_public_subnet(ec2)
# Create a new Elastic IP
elastic_ip_allocation_id = allocate_new_elastic_ip(ec2)
write_file(ELASTIC_IP_ALLOC_ID_PATH, elastic_ip_allocation_id)
# Create a private subnet where instances should be placed.
private_subnet_id = create_private_subnet(ec2)
write_file(PRIVATE_SUBNET_ID_PATH, private_subnet_id)
# Create the NAT Gateway
nat_gateway_id = create_nat_gateway(ec2,public_subnet_id, elastic_ip_allocation_id, private_subnet_id)
write_file(NAT_GATEWAY_ID_PATH, nat_gateway_id)
####################################################

#Get User data
with open("scripts/MySQL_user_data.sh", 'r') as file:
      MySQL_user_data = file.read()

#Launch the EC2 instances
print("Launching MySQL cluster instances...")
roles = ['Manager', 'Worker1', 'Worker2'] 
# Dictionary to store instance IPs

# Loop to create instances with specified roles and congigure MySQL server on them (+ sakila database installation and benchmarking)
for role in roles:
    # Launch instance with the role-specific tag
    print(f"Creating the {role} instance...")
    instance_ip = launch_ec2_instance(ec2,KEY_PAIR_NAME,workers_grp_id,subnet_id=private_subnet_id,user_data=MySQL_user_data,tag=("MySQL_CLUSTER", role))
    
time.sleep(150) # Wait for the setup to be complete

########################## Create the proxy instance ######################## 
print("Creating the Proxy instance...")
Proxy_user_data = get_proxy_user_data(aws_access_key_id, aws_secret_access_key, aws_session_token)
proxy_instance_ip = launch_ec2_instance(ec2,KEY_PAIR_NAME,proxy_grp_id,subnet_id=private_subnet_id,instance_type="t2.large",user_data=Proxy_user_data,tag=("MySQL_CLUSTER", "Proxy"))
######################## Create the trusted host instance ######################## 
print("Creating the Trusted Host instance...")
MySQL_user_data = get_trusted_host_user_data(aws_access_key_id, aws_secret_access_key, aws_session_token)
trusted_host_instance_ip = launch_ec2_instance(ec2,KEY_PAIR_NAME,trustedhost_grp_id,subnet_id=private_subnet_id,instance_type="t2.large",user_data=MySQL_user_data,tag=("MySQL_CLUSTER", "Trusted_Host"))
######################## Create the gatekeeper instance ######################## 
print("Creating the Gatekeeper instance...")
Gatekeeper_user_data = get_gatekeeper_user_data(aws_access_key_id, aws_secret_access_key, aws_session_token)
gatekeeper_instance_ip = launch_ec2_instance(ec2, KEY_PAIR_NAME,gatekeeper_grp_id,subnet_id=public_subnet_id,instance_type="t2.large",public_ip=True,user_data=Gatekeeper_user_data,tag=("MySQL_CLUSTER", "Gatekeeper"))
time.sleep(120)
print("MySQL cluster setup complete.")

######################## Securing the trusted host ######################## 
print("Securing the Trusted Host...")
SECURITY_FILE_PATH = "scripts\TrustedHost_security.sh"
upload_from_gatekeeper(gatekeeper_instance_ip, proxy_instance_ip,trusted_host_instance_ip, key_pair_path,SECURITY_FILE_PATH)
print("MySQL cluster is now secure.")      