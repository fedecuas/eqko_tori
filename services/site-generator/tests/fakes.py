from site_generator.deploy import DeployResult, SiteDeployer


class StubDeployer(SiteDeployer):
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.deploy_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []
        self._counter = 0

    def deploy(self, html: str, slug: str) -> DeployResult:
        self.deploy_calls.append((html, slug))
        if self._error:
            raise self._error
        self._counter += 1
        return DeployResult(url=f"https://{slug}.vercel.app", deployment_id=f"dpl_{self._counter}")

    def delete(self, deployment_id: str) -> None:
        self.delete_calls.append(deployment_id)
