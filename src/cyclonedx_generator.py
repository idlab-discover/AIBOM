import sys
from datetime import datetime
from typing import TYPE_CHECKING
import json
from cyclonedx.model import HashType, XsUri, HashAlgorithm
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model.contact import OrganizationalEntity
from cyclonedx.model.tool import Tool
from cyclonedx.output.json import JsonV1Dot5
from cyclonedx.output import make_outputter, OutputFormat
from cyclonedx.validation.json import JsonStrictValidator
from cyclonedx.exception import MissingOptionalDependencyException
from cyclonedx.model import Property
from cyclonedx.factory.license import LicenseFactory
from cyclonedx.schema import SchemaVersion
from cyclonedx.output import BaseOutput, OutputFormat
import os

if TYPE_CHECKING:
    from cyclonedx.output.json import Json as JsonOutputter
    from cyclonedx.validation.json import JsonValidator


def generate_cyclonedx_format(aibom, output_folder):
    bom = Bom()
    lc_factory = LicenseFactory()

    bom.metadata.tools.components.add(
        Component(
            name="AIBoMGen",
            version="0.1.0",
            type=ComponentType.PLATFORM,
            supplier=OrganizationalEntity(
                name="Ghent University",
                urls=[XsUri('https://www.ugent.be/')]
            ),
            group="Ghent University",
            licenses=[lc_factory.make_from_string('MIT')],
        )
    )

    # Model component (main model)
    model_component = Component(
        type=ComponentType.MACHINE_LEARNING_MODEL,
        name=aibom.get("model_name", "Unknown Model"),
        description=aibom.get("description", "No description available"),
        bom_ref="ai-model",
        properties=[
            Property(name="category", value="custom-training")
        ],
    )
    bom.components.add(model_component)

    installed_components = []  # Store installed components for dependencies
    # Installed Packages (Dependencies)
    for package, version in aibom.get("installed_packages", {}).items():
        library_component = Component(
            type=ComponentType.LIBRARY,
            name=package,
            version=version if version else "unknown",  # Use actual version or "unknown" if missing
            bom_ref=f"package-{package}",  # Unique reference for each package
        )
        bom.components.add(library_component)
        installed_components.append(library_component)  # Add to the list of dependencies

    # Docker Image Details
    if "docker_image" in aibom:
        docker_image = aibom["docker_image"]

        docker_component = Component(
            type=ComponentType.CONTAINER,
            name=docker_image.get("image_name", "Unknown Image"),
            version=docker_image.get("image_version", "Unknown Version"),
            bom_ref="docker-image",
            properties=[
                Property(name="base_image", value=docker_image.get("base_image", "Unknown Base Image")),
                Property(name="layers", value=str(docker_image.get("layers", []))),  # Convert list to string
                Property(name="environment_variables", value=str(docker_image.get("env_variables", []))),  # Convert list to string
                Property(name="cmd", value=str(docker_image.get("cmd", []))),  # Convert list to string
                Property(name="entrypoint", value=docker_image.get("entrypoint", None)),
                Property(name="working_dir", value=docker_image.get("working_dir", "/app")),
                Property(name="volumes", value=str(docker_image.get("volumes", []))),  # Convert list to string
                Property(name="exposed_ports", value=str(docker_image.get("exposed_ports", []))),  # Convert list to string
                Property(name="filesystem_changes", value=str(docker_image.get("filesystem_changes", [])))  # Convert list to string
            ]
        )
        bom.components.add(docker_component)

# Mounted Data Access (Datasets)
    dataset_components = []  # Store dataset components for dependencies
    # Add mounted data access as dataset components
    for file_entry in aibom.get("mounted_data_access", []):
        dataset_component = Component(
            type=ComponentType.DATA,
            name=file_entry.get("file", "Unknown File"),
            description="Dataset used for training",
            bom_ref=f"dataset-{file_entry.get('hash', 'unknown')}",
        )
        dataset_hash = HashType(alg=HashAlgorithm("SHA-256"), content=file_entry.get("hash", "unknown"))
        dataset_component.hashes.add(dataset_hash)
        dataset_component.properties.add(Property(name="dataset-hash", value=file_entry.get("hash", "unknown")))
        dataset_component.properties.add(Property(name="file-path", value=file_entry.get("file", "Unknown File")))

        bom.components.add(dataset_component)
        dataset_components.append(dataset_component)  # Add to the list of dependencies


# GPU Information
    if "gpu_info" in aibom:
        gpu_component = Component(
            type=ComponentType.DEVICE,
            name="Hardware",
            description=f"Training executed on {aibom['gpu_info']}",
            bom_ref="gpu-info",
        )
        bom.components.add(gpu_component)

    # Register dependencies for model_component
    bom.register_dependency(model_component, installed_components + dataset_components)

    # Generate JSON output
    my_json_outputter: 'JsonOutputter' = JsonV1Dot5(bom)
    serialized_json = my_json_outputter.output_as_string(indent=4)

    # Manually format the output using json.dumps() to pretty print it
    pretty_json = json.dumps(json.loads(serialized_json), indent=4)

    # Validation
    my_json_validator = JsonStrictValidator(SchemaVersion.V1_6)
    try:
        validation_errors = my_json_validator.validate_str(pretty_json)
        if validation_errors:
            print('JSON invalid', 'ValidationError:', repr(validation_errors), sep='\n', file=sys.stderr)
            sys.exit(2)
        print('JSON valid')
    except MissingOptionalDependencyException as error:
        print('JSON-validation was skipped due to', error)

    # Define the output file path
    aibom_file_path = os.path.join(output_folder, "aibom.json")

    # Try to write the JSON output to the file
    try:
        with open(aibom_file_path, "w") as file:
            file.write(pretty_json)
    except FileExistsError:
        print(f"File {aibom_file_path} already exists, overwriting...")
        os.remove(aibom_file_path)  # Remove existing file before writing new one
        with open(aibom_file_path, "w") as file:
            file.write(pretty_json)
    finally:
        print(f"Final AIBoM generated at {aibom_file_path}")


