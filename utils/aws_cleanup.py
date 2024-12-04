from utils.constants import *
from shutil import rmtree
from utils.aws_setup import get_path

def cleanup(ec2,sec_group_names, nat_gateway_id, private_subnet_id, allocation_id):
    terminate_instances(ec2)
    
    delete_key(ec2,KEY_PAIR_NAME)
    for sec_group in sec_group_names:
        delete_security_group(ec2,sec_group)
    delete_nat_gateway_and_subnet_and_route_table(ec2,nat_gateway_id, private_subnet_id)
    delete_misc_files()
    release_elastic_ip(ec2,allocation_id)
    
############################################################################################################

def delete_key(ec2,keyName):
    """Delete the key pair with the given name """
    ec2.delete_key_pair(KeyName=keyName)
    # path = get_path(KEY_PAIR_PATH)
    # rmtree(path)
    # print(f"Deleted key pair file")
    print(f"Deleted key {keyName}")
############################################################################################################

def delete_security_group(ec2,group_name):
    """Delete the security group with the given name """
    ec2.delete_security_group(GroupName=group_name)
    print(f"Deleted security group {group_name}")
############################################################################################################
def delete_misc_files():
    path = get_path(CONFIGS_PATH)
    rmtree(path)
    print(f"Deleted configuration files")


def terminate_instances(ec2):
    """ Terminate all instances """
    # Get information about all instances
    response = ec2.describe_instances()

    # Collect all instance IDs
    instance_ids = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_ids.append(instance["InstanceId"])

    if instance_ids:
        # Terminate all instances
        print(f"Terminating instances: {instance_ids}")
        ec2.terminate_instances(InstanceIds=instance_ids)
        print("Termination in progress...")
        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=instance_ids)
        print("Instances termination done")
        
    else:
        print("No instances to terminate.")
############################################################################################################

def get_route_table_id_for_subnet(ec2,subnet_id):
    """Get the route table ID associated with the given subnet """
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
        raise Exception(f"No route table found for subnet {subnet_id}")
############################################################################################################    

def delete_nat_gateway_and_subnet_and_route_table(ec2,nat_gateway_id, private_subnet_id):
    """Delete the NAT Gateway, private subnet, and associated route table """
    try:
        # Step 1: Get the route table associated with the private subnet
        route_table_id = get_route_table_id_for_subnet(ec2,private_subnet_id)  # Assumes this helper function exists

        if route_table_id:
            # Disassociate all route table associations except the main route table
            response = ec2.describe_route_tables(RouteTableIds=[route_table_id])
            associations = response['RouteTables'][0].get('Associations', [])
            for association in associations:
                if not association['Main']:  # Skip the main route table
                    ec2.disassociate_route_table(AssociationId=association['RouteTableAssociationId'])
                    print(f"Disassociated {association['RouteTableAssociationId']} from route table {route_table_id}")
            
            # Delete routes in the route table (if any)
            try:
                ec2.delete_route(
                    RouteTableId=route_table_id,
                    DestinationCidrBlock='0.0.0.0/0'
                )
                print(f"Deleted route to NAT Gateway from route table {route_table_id}.")
            except ec2.exceptions.ClientError as e:
                if "InvalidRoute.NotFound" in str(e):
                    print(f"No route to delete in route table {route_table_id}.")
                else:
                    print(f"Error deleting route: {e}")

            # Delete the route table
            try:
                ec2.delete_route_table(RouteTableId=route_table_id)
                print(f"Successfully deleted route table: {route_table_id}")
            except ec2.exceptions.ClientError as e:
                print(f"Error deleting route table: {e}")
        else:
            print("No route table associated with the provided subnet.")

        # Step 2: Delete the NAT Gateway
        try:
            ec2.delete_nat_gateway(NatGatewayId=nat_gateway_id)
            print(f"Deleting NAT Gateway: {nat_gateway_id}")

            # Wait for NAT Gateway deletion to complete
            waiter = ec2.get_waiter('nat_gateway_deleted')
            waiter.wait(NatGatewayIds=[nat_gateway_id])
            print(f"NAT Gateway {nat_gateway_id} has been deleted.")
        except ec2.exceptions.ClientError as e:
            print(f"Error deleting NAT Gateway: {e}")

        # Step 3: Delete the private subnet
        try:
            ec2.delete_subnet(SubnetId=private_subnet_id)
            print(f"Deleted private subnet: {private_subnet_id}")
        except ec2.exceptions.ClientError as e:
            print(f"Error deleting private subnet: {e}")

    except Exception as e:
        print(f"Unexpected error: {e}")
############################################################################################################

def release_elastic_ip(ec2,allocation_id):
    """Release the Elastic IP address """
    # Release the Elastic IP
    print(f"Releasing Elastic IP with allocation ID: {allocation_id}")
    ec2.release_address(AllocationId=allocation_id[0])
    print("Elastic IP released successfully.")

def delete_route_table(ec2,private_subnet_id):
    """Delete the route table associated with the private subnet """
    route_table_id = get_route_table_id_for_subnet(private_subnet_id)

    # Check and disassociate all associations
    response = ec2.describe_route_tables(RouteTableIds=[route_table_id])
    associations = response['RouteTables'][0].get('Associations', [])
    for association in associations:
        if not association['Main']:  # Don't disassociate the main route table
            ec2.disassociate_route_table(AssociationId=association['RouteTableAssociationId'])
            print(f"Disassociated {association['RouteTableAssociationId']} from route table {route_table_id}")

    # Delete the route table
    ec2.delete_route_table(RouteTableId=route_table_id)
    print(f"Successfully deleted route table: {route_table_id}")
############################################################################################################    
    