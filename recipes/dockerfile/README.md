Reuse the existing Dockerfile without modifying it. Review its build instructions,
base image digests, build context and runtime before building. The descriptor must
name a Python or Node runtime already present in the image for the isolated HTTP
health probe. Images requiring another probe runtime are currently unsupported.

No recipe runs dependency installers or application build/test commands. The
explicit verification action runs the selected image with no network access,
credentials or mounts. External-service readiness needs separate OCI verification.
