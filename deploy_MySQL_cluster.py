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
def sftp_upload(sftp_client,local_file_path , remote_path):
    # Upload the file
    sftp_client.put(local_file_path, remote_path)
    print(f"Successfully uploaded files")
###############################################################  
def upload_from_gatekeeper(gatekeeper_ip,proxy_ip, private_ip, key_pair_path,local_file_path):
    remote_directory = "/home/ubuntu/my_project"
    # key_path = get_path(key_file)
    private_key = paramiko.RSAKey.from_private_key_file(key_pair_path)

    # Set up SSH connection to the gatekeeper
    gatekeeper_client = paramiko.SSHClient()
    gatekeeper_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    gatekeeper_client.connect(gatekeeper_ip, username='ubuntu', pkey=private_key)

    # SSH tunnel to private instance via gatekeeper
    gatekeeper_transport = gatekeeper_client.get_transport()
    dest_addr = (private_ip, 22)  # Private EC2 instance IP and SSH port
    local_addr = ('0.0.0.0', 0)
    
    # Separate SSH client for the private instance
    private_client = paramiko.SSHClient()
    private_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        tunnel = gatekeeper_transport.open_channel('direct-tcpip', dest_addr, local_addr)
        private_client.connect(private_ip, username='ubuntu', pkey=private_key, sock=tunnel)
        print("SSH is available!")
    except (paramiko.SSHException, Exception) as e:
        print(f"SSH not available yet: {e}")
        time.sleep(3)  # Wait before retrying
    
    # Use SFTP to upload the bash script to the private instance
    sftp_client = private_client.open_sftp()      

    try:
        # Upload the security file to the private instance
        print("Uploading security file to the trusted host...")
        remote_file_path = remote_directory + "/security.sh"
        print(f"Uploading file to {remote_file_path}")
        try:
            remote_file_path = remote_directory + "/security.sh"
            sftp_client.put(local_file_path, remote_file_path)
            print(local_file_path)
            print(f"File uploaded to {remote_file_path}")
        except Exception as e:
             print(f"Failed to upload file via SFTP: {e}")
        #Pass gatekeeper_instance_ip and trusted_host_instance_ip as arguments to the script
        command = (
            f"chmod +x {remote_file_path} && "
            f"nohup {remote_file_path} {gatekeeper_ip} {proxy_ip} > {remote_directory}/security.log 2>&1 &"
        )
        # private_client.set_combine_stderr(True)
        stdin, stdout, stderr = private_client.exec_command(command)
        # Output ssh
        channel = stdout.channel  # Get the Channel object for monitoring

        # Wait for the command to complete and stream output
        while not channel.exit_status_ready():
            # Use select to check if there's data to read
            if channel.recv_ready():
                print(channel.recv(1024).decode("utf-8"), end="")  # Print command output
        print(f"Security script executed successfully on {private_ip} with arguments: "
              f"{gatekeeper_ip}, {proxy_ip}.")
    except Exception as e:
        print("Failed secure the trusted host: {e}")

    # Close SFTP and SSH connection
    sftp_client.close()
    private_client.close()
    tunnel.close()

  
print("Securing the Trusted Host...")
SECURITY_FILE_PATH = "scripts\TrustedHost_security.sh"
upload_from_gatekeeper(gatekeeper_instance_ip, proxy_instance_ip,trusted_host_instance_ip, key_pair_path,SECURITY_FILE_PATH)
print("MySQL cluster is now secure.")      