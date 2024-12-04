## Constants
KEY_PAIR_NAME = 'log8415E-tp3-key-pair'
KEY_PAIR_PATH ='temp\\' + KEY_PAIR_NAME + '.pem'
SECURITY_GROUP_NAME = 'log8415E'

GATEKEEPER_SG_NAME = "gatekeeper_group"
TRUSTEDHOST_SG_NAME = "trustedhost_group"
PROXY_SG_NAME = "proxy_group"
WORKERS_SG_NAME = "workers_group"


CONFIGS_PATH = "configs"
NAT_GATEWAY_ID_PATH = CONFIGS_PATH + "/nat_gateway_id.txt"
PRIVATE_SUBNET_ID_PATH = CONFIGS_PATH + "/private_subnet_id.txt"
ELASTIC_IP_ALLOC_ID_PATH = CONFIGS_PATH + "/elastic_ip_aloc_id.txt"
BASTION_INFO_PATH = CONFIGS_PATH + "/instance_info_bastion.json"

SECURITY_SCRIPT_PATH = "scripts/TrustedHost_security.sh"  