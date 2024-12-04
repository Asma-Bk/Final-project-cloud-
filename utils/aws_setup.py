# Description: This file contains utility functions to create and manage AWS resources such as EC2 instances, security groups, key pairs, etc.

# Necessary imports
import os
from pathlib import Path
import boto3
import paramiko
import time
###############################################################
def get_path(file_path):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, file_path)
###############################################################
def write_file(file_path: str, data: str):
    filename = get_path(file_path)
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as file:
        file.write(data)

###############################################################
# Generate a key pair
def generate_key_pair(ec2_client, key_pair_name, out_path = "temp"):
    """Generate a new key pair and save it to a file"""
    key_pair_path = Path(os.path.join(out_path, f'{key_pair_name}.pem'))
    if key_pair_path.exists():
        print(f"Key pair '{key_pair_name}' already exists.")
        return key_pair_path
    response = ec2_client.create_key_pair(KeyName=key_pair_name)

    # Save the private key to a file
    private_key = response['KeyMaterial']
    Path(out_path).mkdir(exist_ok=True)
    with open(key_pair_path, 'w') as key_file:
        key_file.write(private_key)

    print(f"Key pair '{key_pair_name}' has been created and saved to {key_pair_name}.pem")

    return str(key_pair_path)


###############################################################
def create_security_group(ec2_client, group_name, group_description,rules_in):
    """Create a new security group with the specified name and description"""
    # Check if security group already exists
    existing_groups = ec2_client.describe_security_groups(
        Filters=[
            {'Name': 'group-name', 'Values': [group_name]}
        ]
    )['SecurityGroups']

    if existing_groups:
        # If the group exists, return its ID
        print(f"Security group '{group_name}' already exists.")
        return existing_groups[0]['GroupId']

    # If the group doesn't exist, create a new one
    print("Creating security group...")
    # Create the security group
    response = ec2_client.create_security_group(
        GroupName=group_name, Description=group_description
    )
    security_group_id = response["GroupId"]
    print(f"Security Group '{group_name}' created with ID: {security_group_id}")

    # Allow ingress
    ec2_client.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=rules_in
    )
    print(f"Configured Security Group's '{group_name}' authorizations")
    return security_group_id
###############################################################
# Launch an EC2 instance
def launch_ec2_instance(ec2, 
                    key_pair_name, 
                    security_group_id,
                    subnet_id = None,
                    instance_type:str = "t2.micro", 
                    num_instances:int = 1, 
                    image_id:str =  "ami-0e86e20dae9224db8",
                    public_ip:bool = False,
                    user_data = "",
                    tag:tuple[str,str] = None,
                    ):
    
    """Launch an EC2 instance with the specified parameters"""    
    # Specify instance parameters
    instance_params = {
        'ImageId': image_id, 
        'InstanceType': instance_type,
        'MinCount': num_instances,
        'MaxCount': num_instances,
        'KeyName': key_pair_name,
        'NetworkInterfaces': [{
            'AssociatePublicIpAddress': public_ip,
            'DeviceIndex': 0,
            'Groups': [security_group_id],
            'SubnetId': subnet_id
        }],
    }
    if tag is not None:
        instance_params["TagSpecifications"] = [
            {"ResourceType": "instance", "Tags": [{"Key": tag[0], "Value": tag[1]}]}]
   
    # Launch the instance
    response = ec2.run_instances(UserData=user_data, **instance_params)
    
    ec2_resource = boto3.resource('ec2') 
    instance_id = response['Instances'][0]['InstanceId']
    instance = ec2_resource.Instance(instance_id)
    print(f"Launching instance {instance_id}...")
    instance.wait_until_running()
    if public_ip:
        instance_ip = instance.public_ip_address
        print(f"Instance {instance_id} is running with public IP: {instance_ip}")
    else:
        instance_ip = instance.private_ip_address
        print(f"Instance {instance_id} is running with private IP: {instance_ip}")    
    return  instance_ip
###############################################################
def get_instances_by_tag(ec2,tag_key, tag_value):
    """ Get the IP address of an instance with a specific tag"""
    response = ec2.describe_instances(
        Filters=[
            {
                "Name": f"tag:{tag_key}",
                "Values": [tag_value]
            },
            {
                "Name": "instance-state-name",
                "Values": ["running"]
            }
        ]
    )

    if len(response["Reservations"]) == 0:
        return []
    instance_ip = response['Reservations'][0]["Instances"][0]["PrivateIpAddress"] 
    return instance_ip
######################## Utilities to create a Nat Gateway #######################################
def create_nat_gateway(ec2, public_subnet_id, elastic_ip_allocation_id, private_subnet_id):
    """Create a NAT Gateway in the public subnet and set up routing in the private subnet"""
    response = ec2.create_nat_gateway(
        SubnetId=public_subnet_id,
        AllocationId=elastic_ip_allocation_id
    )
    
    nat_gateway_id = response['NatGateway']['NatGatewayId']
    print(f"NAT Gateway created: {nat_gateway_id}")
    print("Waiting fot the NAT Gateway to become available...")
    waiter = ec2.get_waiter('nat_gateway_available')
    waiter.wait(NatGatewayIds=[nat_gateway_id])
    print("NAT Gateway is now available !")

    # Get the Route Table ID for the private subnet
    private_subnet_route_table_id = get_route_table_id_for_subnet(ec2,private_subnet_id)
    
    # Create a route in the private subnet's route table to route traffic through the NAT Gateway
    ec2.create_route(
        RouteTableId=private_subnet_route_table_id,
        DestinationCidrBlock='0.0.0.0/0',  # Route all traffic to the NAT Gateway
        NatGatewayId=nat_gateway_id
    )
    print(f"Route created in route table {private_subnet_route_table_id} to NAT Gateway {nat_gateway_id}")
    # Return the NAT Gateway ID and Route Table ID
    return nat_gateway_id
###############################################################
def find_public_subnet(ec2, availability_zone='us-east-1c'):
    """ Find a public subnet where the NAT Gateway will be placed """
    # Describe all subnets and filter for public ones in the specified Availability Zone
    response = ec2.describe_subnets(
        Filters=[
            {'Name': 'map-public-ip-on-launch', 'Values': ['true']},  # Public subnets
            {'Name': 'availability-zone', 'Values': [availability_zone]}  
        ]
    )
    public_subnet_id = response['Subnets'][0]['SubnetId']
    print(f"Public Subnet ID: {public_subnet_id}")
    return public_subnet_id

def allocate_new_elastic_ip(ec2):
    """Allocate a new Elastic IP address """
    response = ec2.allocate_address(Domain='vpc')
    print(f"New Elastic IP: {response['PublicIp']}, Allocation ID: {response['AllocationId']}")
    return response['AllocationId']

def create_private_subnet(ec2,cidr_block = '172.31.96.0/20', availability_zone = "us-east-1c"):       #  172.31.96.0/20 is not yet assigned, and it is part of the 172.31.x.x range of the VPC
    """Create a private subnet in the default VPC"""
    # Step 1: Find the VPC ID
    vpcs = ec2.describe_vpcs()
    vpc_id = vpcs['Vpcs'][0]['VpcId']

    print(f"Using VPC ID: {vpc_id}")

    # Step 2: Create the Subnet
    subnet_response = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock=cidr_block,
        AvailabilityZone=availability_zone
    )
    subnet_id = subnet_response['Subnet']['SubnetId']
    print(f"Created private subnet with ID: {subnet_id}")

    # Step 3: Disable Auto-assign Public IPs
    ec2.modify_subnet_attribute(
        SubnetId=subnet_id,
        MapPublicIpOnLaunch={'Value': False}
    )
    print(f"Disabled auto-assign public IP for subnet: {subnet_id}")

    return subnet_id
###############################################################
def get_vpc_id_from_subnet(ec2,subnet_id):
    """ Get VPC ID from a subnet ID"""
    response = ec2.describe_subnets(SubnetIds=[subnet_id])
    vpc_id = response['Subnets'][0]['VpcId']
    return vpc_id
###############################################################
def get_route_table_id_for_subnet(ec2,subnet_id):
    """ Get Route Table ID for a subnet. If no route table is associated with the subnet, create a new one and associate it."""
    # Describe the route tables and filter by subnet ID
    response = ec2.describe_route_tables(
        Filters=[
            {
                'Name': 'association.subnet-id',
                'Values': [subnet_id]
            }
        ]
    )
    
    # If a route table is associated with the subnet, return the Route Table ID
    if response['RouteTables']:
        route_table_id = response['RouteTables'][0]['RouteTableId']
        return route_table_id
    else:
        # If no route table is found, create a new one and associate it with the subnet
        print(f"No route table found for subnet {subnet_id}, creating a new route table.")

        vpc_id = get_vpc_id_from_subnet(ec2,subnet_id)   # Extract VPC ID from subnet_id
        route_table_response = ec2.create_route_table(
            VpcId=vpc_id  
        )
        new_route_table_id = route_table_response['RouteTable']['RouteTableId']
        
        # Associate the new route table with the subnet
        ec2.associate_route_table(
            RouteTableId=new_route_table_id,
            SubnetId=subnet_id
        )
        print(f"Created and associated route table {new_route_table_id} with subnet {subnet_id}")
        return new_route_table_id
    
###############################################################   
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

  