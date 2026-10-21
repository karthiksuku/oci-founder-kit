# Security

The kit reads local files you point it at and calls one public, unauthenticated
endpoint: Oracle's price list API. It never needs OCI credentials, cloud
account access or API keys.

- Keep invoices, billing exports, scenarios and reports out of Git. The
  `.gitignore` excludes a `work/` folder for them.
- Do not paste credentials, customer contracts or personal data into prompts
  or scenario files; the model needs amounts, not identities.
- Report a vulnerability privately to the maintainer rather than in a public
  issue.
