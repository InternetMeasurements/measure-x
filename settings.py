import subprocess
import time
import json
import getpass
import sys
from string import Template

def generate_from_template(template_path, output_path, context):
    """Read a template, substitute variables and write the final file"""
    try:
        with open(template_path, 'r') as f:
            src = Template(f.read())
            result = src.substitute(context)
        
        with open(output_path, 'w') as f:
            f.write(result)
        print(f"Generated: {output_path}")
        
    except FileNotFoundError:
        print(f"Error: Template '{template_path}' not found")
        sys.exit(1)
    except KeyError as e:
        print(f"Error: field {e} not provided in context")
        sys.exit(1)

def wait_for_mongo(container_name, max_retries=30):
    """Polls the container until Mongo is ready to accept connections"""
    print(f"Waiting for MongoDB ({container_name}) to be ready...")
    for i in range(max_retries):
        try:
            subprocess.check_call(
                ["docker", "exec", container_name, "mongosh", "--eval", "db.runCommand('ping')"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("MongoDB is up and running!")
            return
        except subprocess.CalledProcessError:
            time.sleep(2)
    
    print("Timeout waiting for MongoDB.")
    sys.exit(1)

print("Please provide configuration details.")
password = getpass.getpass("Password for MongoDB user 'measurex': ")

if not password:
    print("Password cannot be empty.")
    sys.exit(1)

data_context = {
    'password': password
}

generate_from_template(
    'grafana/datasources/datasource.yaml.template', 
    'grafana/datasources/datasource.yaml', 
    data_context
)

generate_from_template(
    'coordinatorConfig.yaml.template', 
    'coordinatorConfig.yaml', 
    data_context
)

print("Starting Docker containers...")
try:
    subprocess.run(['docker', 'compose', 'up', '-d', '--build'], check=True)
except subprocess.CalledProcessError:
    print("Failed to start Docker Compose.")
    sys.exit(1)

CONTAINER_NAME = "measure-x-mongo"
wait_for_mongo(CONTAINER_NAME)

safe_password = json.dumps(password)
safe_user = json.dumps('measurex')

mongo_script = f"""
    let user = {safe_user};
    let pwd = {safe_password};
    let roles = [{{ role: 'readWrite', db: 'measurex' }}];

    if (db.getUser(user)) {{
        db.updateUser(user, {{ pwd: pwd, roles: roles }});
        print('User ' + user + ' updated successfully.');
    }} else {{
        db.createUser({{ user: user, pwd: pwd, roles: roles }});
        print('User ' + user + ' created successfully.');
    }}
"""

print("Configuring MongoDB user...")
subprocess.run([
    "docker", "exec", CONTAINER_NAME,
    "mongosh", "admin",
    "--eval", mongo_script
], check=True)

print("\nEnvironment setup complete!")
