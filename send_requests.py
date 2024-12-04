# import requests

# #Set the URL and parameters
# Gatekeeper_instance_ip = "35.175.251.182" 
# url = "http://"+Gatekeeper_instance_ip+"/database"
# params = {'strategy': 'random'}

# # The query you want to send
# write_query="INSERT INTO sakila.customer (store_id, first_name, last_name, email, address_id, active, create_date) VALUES (1, 'Asma', 'Boukhdhir', 'asma.boukhdhir@example.com', 5, 1, NOW());"
# read_query = "SELECT * FROM sakila.customer WHERE first_name = 'Asma' AND last_name = 'Boukhdhir' LIMIT 1;"

# headers = {
#     'x-api-key': 'LOG8415E'
# } 
# # Send the request
# response = requests.post(url, params=params, data=read_query, headers=headers)

# # Print the response
# print(response.json())

import requests
from concurrent.futures import ThreadPoolExecutor
import time

# Set up the Gatekeeper instance and API details
Gatekeeper_instance_ip = "44.195.0.176"
url = f"http://{Gatekeeper_instance_ip}/database"
headers = {'x-api-key': 'LOG8415E'}

# Define the queries
write_query_template = (
    "INSERT INTO sakila.customer "
    "(store_id, first_name, last_name, email, address_id, active, create_date) "
    "VALUES (1, 'John', 'Doe', 'johndoe{}@example.com', 5, 1, NOW());"
)
read_query = "SELECT COUNT(*) FROM sakila.film;"

# Function to send write requests
def send_write_request(request_id, strategy):
    query = write_query_template.format(request_id)  # Unique email for each request
    params = {'strategy': strategy}
    response = requests.post(url, params=params, data=query, headers=headers)
    return f"Write Request {request_id}: {response.json()}"


# Function to send read requests
def send_read_request(request_id, strategy):
    params = {'request_id': request_id,'strategy': strategy,}
    response = requests.post(url, params=params, data=read_query, headers=headers)
    return f"Read Request {request_id}: {response.json()}"

# Main function to send 1000 write and 1000 read requests
def main(strategy):
    num_requests = 1000# Total number of requests for write and read
    start_time = time.time()

    #ThreadPoolExecutor to send requests concurrently
    with ThreadPoolExecutor(max_workers=50) as executor:
        write_futures = [executor.submit(send_write_request, i+1, strategy) for i in range(num_requests)] # Send write requests
        read_futures = [executor.submit(send_read_request, i+1, strategy) for i in range(num_requests)] # Send read requests
        write_responses = [future.result() for future in write_futures] # Get write responses
        read_responses = [future.result() for future in read_futures] # Get read responses

    end_time = time.time()
    duration = end_time - start_time

    print("\n".join(write_responses[:10]))  # Show only the first 10 for brevity
    print("\n".join(read_responses[:10]))

   
    print(f"\nCompleted {num_requests} write and {num_requests} read requests in {duration:.2f} seconds.")  # Print summary

if __name__ == "__main__":
    # Parse the strategy argument
    parser = argparse.ArgumentParser(description="Send requests to the Gatekeeper with a specific strategy for the proxy.")
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help="The strategy to use for the requests ('direct,'random', 'customized')."
    )
    args = parser.parse_args()

    # Execute the main function with the provided strategy
    main(args.strategy)

