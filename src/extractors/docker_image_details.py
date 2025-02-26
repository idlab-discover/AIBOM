import json
import docker
import subprocess
from docker.errors import ImageNotFound

client = docker.from_env()

def extract_docker_image_details(container):
    details = {}

    try:
        image = client.images.get(container.image.id)
        image_name = image.tags[0] if image.tags else image.id
        print(f"Extracting details for image: {image_name}")
        image_version = image_name.split(":")[1] if ":" in image_name else "latest"
        details["image_name"] = image_name
        details["image_version"] = image_version

        # Extract base image & layers
        details["base_image"] = image.attrs.get("Config", {}).get("Image", "Unknown")
        details["layers"] = [layer for layer in image.attrs.get("RootFS", {}).get("Layers", [])]

        # Extract exposed ports
        details["exposed_ports"] = list(image.attrs.get("Config", {}).get("ExposedPorts", {}).keys() or [])

        # Extract environment variables
        details["env_variables"] = image.attrs.get("Config", {}).get("Env", [])

        # Extract CMD & ENTRYPOINT
        details["cmd"] = image.attrs.get("Config", {}).get("Cmd", [])
        details["entrypoint"] = image.attrs.get("Config", {}).get("Entrypoint", [])

        # Extract working directory
        details["working_dir"] = image.attrs.get("Config", {}).get("WorkingDir", "Unknown")

        # Extract volumes
        volumes = image.attrs.get("Config", {}).get("Volumes", {})
        details["volumes"] = list(volumes.keys()) if volumes else []

        # Extract system packages (Debian-based: dpkg, Red Hat-based: rpm)
        # system_packages_cmd = "dpkg -l || rpm -qa"
        # system_packages_result = container.exec_run(["sh", "-c", system_packages_cmd])
        # details["system_packages"] = system_packages_result.output.decode().strip().split("\n")

        # Extract filesystem changes in the running container
        diff_result = client.containers.get(container.id).diff()
        details["filesystem_changes"] = [change["Path"] for change in diff_result]

    except docker.errors.ImageNotFound:
        details["error"] = f"Image {container.image.id} not found."
    except Exception as e:
        details["error"] = str(e)

    return details