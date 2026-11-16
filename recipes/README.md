# Package your existing application

These additive recipes prepare **Next.js standalone**, **FastAPI**, or an
**existing Dockerfile** for the generic web-container target. Existing application
files, data providers, identity providers and framework choices stay intact.
The kit proposes files first. It never executes the descriptor's commands.

The preview requires Docker Buildx/BuildKit and supports Linux AMD64 images with
Python or Node available for the health probe. The legacy Docker builder ignores
Dockerfile-specific exclusions and must not be used for these recipes.
Dependency installation and framework builds run only after the
founder or agent separately reviews the existing application's commands.

1. Select a named rehearsal environment and inspect its packaging choices:

   ~~~sh
   .oci-founder-kit/scripts/oci-kit package inspect --environment rehearsal
   ~~~

2. Create an owner-only JSON descriptor outside Git. Use the following structure,
   replacing the base image placeholder with a reviewed, compatible **real digest**:

   ~~~json
   {
     "schema": "oci-kit-application/1",
     "recipe": "fastapi",
     "app_directory": ".",
     "commands": {
       "build": ["docker", "buildx", "build", "--load", "--file", "Dockerfile.oci", "."],
       "start": ["python", "-m", "uvicorn", "main:app", "--port", "8080"],
       "test": ["python", "-m", "pytest"]
     },
     "port": 8080,
     "health_path": "/health",
     "dependencies": ["DATABASE_URL", "OIDC_ISSUER"],
     "background_work": "source",
     "probe_runtime": "python",
     "base_image": "<reviewed-public-python-image>@sha256:<real-digest>",
     "entrypoint": "main:app"
   }
   ~~~

   Dependency entries are names only. Commands are recorded for review, not run.
   Keep secret values, account identifiers and endpoint configuration in the
   existing private environment configuration.

3. Review and apply the exact additive proposal:

   ~~~sh
   .oci-founder-kit/scripts/oci-kit package propose --environment rehearsal --descriptor /private/app.json
   .oci-founder-kit/scripts/oci-kit package apply --environment rehearsal --approve '<proposal-sha256>'
   ~~~

   This local review authorizes only the displayed packaging files. It never
   authorizes cloud changes. The proposal expires after one hour and refuses
   changed source, changed environments, changed recipe bytes, existing
   destinations, symlinks and unsafe private inputs. Interrupted partial writes
   remain for inspection; the helper will not overwrite them on retry.

4. Review and run your own build and meaningful tests. The proposal supplies the
   build directory and an argument-list command. Build without secret arguments;
   use the application's reviewed secret handling where a build genuinely needs
   credentials. Never put a runtime secret in an image.

5. Prepare a **private, single-platform Docker v2s2 directory transport** from the
   tested immutable image ID using the image guide's
   [local Docker archive and Skopeo conversion commands](../skills/oci-deploy/references/image-publication.md#prepare-the-image-locally).
   These commands do not publish an image. Then run the explicit isolated
   verification action:

   ~~~sh
   .oci-founder-kit/scripts/oci-kit package verify --environment rehearsal \
     --image 'sha256:<local-config-digest>' --layout /private/tested-image-layout
   ~~~

   The verifier checks every compressed layer and rootfs digest through the
   existing publication gate. It scans all layers (including files later
   deleted) and image configuration for recognized credential patterns/private
   paths, then runs the exact local image without network access, credentials,
   host mounts or capabilities. The runtime is non-root, read-only and resource
   bounded. It probes HTTP 200 at the descriptor's loopback health route and
   removes its own temporary container. A failed removal reports retained local
   work for manual inspection.

   A dependency-free liveness route can pass locally. Authentication, persistence,
   external connectivity, browser behavior and restore still require the separate
   environment verification journey. A pattern scan cannot prove that arbitrary
   secrets are absent. The returned **manifest digest**, local image configuration
   digest and private report identify the exact tested artifact. Publication still
   needs its own fresh image-gate plan and exact approval; verification never
   uploads, tags or changes environment deployment settings.

| Recipe | Existing prerequisites | Added files and limits |
|---|---|---|
| Next.js | npm lockfile; one existing Next config selecting standalone output; reviewed Node base digest | Dockerfile.oci and its private-input exclusions. No Next config rewrite. Monorepo tracing, persistent cache, server actions and multi-instance behavior require application-specific review. |
| FastAPI | Hash-locked requirements including uvicorn; explicit existing ASGI callable; reviewed Python base digest | Dockerfile.oci and its exclusions. No source/dependency rewrite. Native libraries and startup migrations require explicit review. |
| Existing Dockerfile | Reviewed external FROM digests; Python or Node already in image | Only a Dockerfile-specific ignore file. Dynamic FROM directives and a nested Dockerfile need manual adaptation in this preview. |

For Next.js, set recipe to nextjs, probe_runtime to node, select the Node base
digest and omit entrypoint. For an existing Dockerfile, select recipe dockerfile,
set dockerfile to its filename, select the available probe runtime and omit
base_image/entrypoint. Choose background_work as absent, disabled, or source;
ownership transfer is a separate reviewed operation.

The generated Dockerfile-specific ignore file preserves the existing
.dockerignore rules and appends exclusions last. It cannot detect every private
filename; review the full context before building.

These are original kit recipes, informed by public documentation reviewed
16 November 2026: [Next.js self-hosting](https://nextjs.org/docs/app/guides/self-hosting),
[Next.js standalone output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output),
and [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).
Local recipe checks do not establish OCI deployment acceptance.
