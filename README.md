# Agentcraft

Reusable agent skills, callable libraries and workflow guidance for application development,
Azure integration, authentication, data access, evaluation and verification.

Start with the [skill catalogue](.github/skills/README.md): 32 capability skills and six embedded
entries, with source, contracts, examples and focused checks. Follow each selected skill's
installation instructions; loading guidance alone does not install dependencies or grant access.

The experimental [Azure data-connector library](libraries/azure-data-connectors/README.md)
provides one async interface for Search and Cosmos, with explicit operation support, policy
and read-back evidence. Its first pass is verified offline; live tests and migration of
existing skill/application consumers are deferred. It is not an in-place `azdata` 3.x upgrade.

A dedicated, empty Azure resource group for future connector E2E tests is created and
read-back verified. The [deployment runbook](deploy/README.md) owns its non-secret targets,
verification evidence and protected lifecycle commands. Service provisioning, sample data
and live CRUD tests remain deferred.

Customer deployment targets and source-project examples have been removed or anonymized from
the skills. The optimization snapshot contains portable source and explicitly synthetic record
examples; the cleanup case study preserves anonymized historical measurements. No capability was
retired by that sanitization. Azure lifecycle commands require an explicit subscription.

The [MIT license](LICENSE) covers repository-authored code. Bundled fonts and artwork retain their
separate notices; external runtime dependencies retain their own terms. Read the
[distribution guidance](.github/skills/AGENT-PLUGINS-SKILLS.md) before publishing a derived package.

## Limits

- Live cloud access, paid model calls and deployments require operator configuration and authorization.
- Offline fixture checks do not establish production permissions or measured model performance.
- This checkout provides skills, not a repository-root plugin installer or an automatically deployed app.
- New contributions, datasets and third-party assets need their own provenance and rights review.

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
