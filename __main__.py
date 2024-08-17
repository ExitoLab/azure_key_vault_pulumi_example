import pulumi, base64
import pulumi_azure_native as azure_native
import pulumi_azure_native.compute as compute
import pulumi_azure_native.network as network
import pulumi_azure_native.resources as resources
import pulumi_azure as azure

from pulumi import Config, export, asset, Output
from pulumi_azure_native.keyvault import get_secret_output

# Create a config object to access configuration values
config = pulumi.Config()

env =  pulumi.get_stack()
appname = pulumi.get_project()

# Get the parameters
location = config.get("location")
key_vault_name = config.get("key_vault_name")
subscription_id = config.get("subscription_id")
resource_group_name = config.get("resource_group_name")
nginx_config_url = config.get("nginx_config_url")
vm_publisher = config.get("vm_publisher")
vm_offer = config.get("vm_offer")
vm_sku = config.get("vm_sku")
vm_version = config.get("vm_version")
vm_name = config.get("vm_name")

resource_group = azure_native.resources.ResourceGroup("resourceGroup",
    location=location,
    resource_group_name=f"{appname}-{env}-rg"
)

# Build the Key Vault ID
key_vault_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.KeyVault/vaults/{key_vault_name}"

# Get the username and password from Azure Key Vault
admin_username = azure.keyvault.get_secret(name="adminUsername",key_vault_id=key_vault_id)
admin_password = azure.keyvault.get_secret(name="adminPassword",key_vault_id=key_vault_id)
git_token = azure.keyvault.get_secret(name="gitToken",key_vault_id=key_vault_id)

# Check if the secrets are empty or invalid
if not admin_username or not admin_password or not git_token:
    raise Exception("Failed to fetch admin credentials from Key Vault.")

# Serialize username,password and git_token
admin_username = admin_username.value
admin_password = admin_password.value

#Create virtual_network
virtual_network = azure_native.network.VirtualNetwork("virtualNetwork",
    address_space={
        "addressPrefixes": ["10.0.0.0/16"],
    },
    flow_timeout_in_minutes=10,
    location=location,
    resource_group_name=resource_group.name,
    virtual_network_name=f"{appname}-{env}-vn")

#Create the subnet
subnet = azure_native.network.Subnet("subnet",
    address_prefix="10.0.0.0/16",
    resource_group_name=resource_group.name,
    subnet_name=f"{appname}-{env}-sn",
    virtual_network_name=virtual_network.name)

# Create a Public IP Address
public_ip = azure_native.network.PublicIPAddress(f"publicIP-{env}",
    resource_group_name=resource_group.name,
    location=location,
    public_ip_allocation_method="Dynamic")

# Create a network interface without a public IP
network_interface = azure_native.network.NetworkInterface("networkInterface-" + env,
    resource_group_name=resource_group.name,
    location=location,
    ip_configurations=[{
        "name": "ipconfig1",
        "subnet": azure_native.network.SubnetArgs(
            id=subnet.id,
        ),
        "public_ip_address": azure_native.network.PublicIPAddressArgs(
            id=public_ip.id,
        ),
    }]
)

# Create the Azure VM
vm = azure.compute.LinuxVirtualMachine("{vm_name}-{env}",
    resource_group_name=resource_group.name,
    location=location,
    network_interface_ids=[network_interface.id],
    size="Standard_B1ms",
    disable_password_authentication=False, 
    admin_username=admin_username,
    admin_password=admin_password,
    os_disk=azure.compute.LinuxVirtualMachineOsDiskArgs(
        storage_account_type="Standard_LRS",
        caching="ReadWrite",
        disk_size_gb=30,
    ),
    source_image_reference=azure.compute.LinuxVirtualMachineSourceImageReferenceArgs(
        publisher=vm_publisher,
        offer=vm_offer,
        sku=vm_sku,
        version=vm_version,
    ),
    custom_data=cloud_init_script_base64,
    tags={"Environment": env}
)

#Export the VM name, resource_group_name and nginx_conf_url of the VM
export("resource_group_name", resource_group.name)
export("vm_name", vm.name)