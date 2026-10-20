from typing import List
from playwright.sync_api import Page, Route


class NetworkGuard:
    """Network sandboxing: permits local loopback assets, intercepts and mocks external egress."""

    def __init__(self, local_base_url: str):
        self.local_base_url = local_base_url.rstrip("/")
        self.intercepted_external_calls: List[str] = []

    def attach(self, page: Page) -> None:
        def handle_route(route: Route):
            req_url = route.request.url
            if req_url.startswith(self.local_base_url) or req_url.startswith("data:"):
                route.continue_()
            else:
                self.intercepted_external_calls.append(req_url)
                rtype = route.request.resource_type
                if rtype == "script":
                    route.fulfill(
                        status=200,
                        content_type="application/javascript",
                        body="/* mocked by html_tester */"
                    )
                elif rtype == "stylesheet":
                    route.fulfill(
                        status=200,
                        content_type="text/css",
                        body="/* mocked by html_tester */"
                    )
                elif rtype == "image":
                    route.fulfill(
                        status=200,
                        content_type="image/svg+xml",
                        body='<svg xmlns="http://www.w3.org/2000/svg"/>'
                    )
                else:
                    # Return safe dummy JSON response for fetch / xhr
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"mocked_by_html_tester": true, "status": "ok"}'
                    )

        page.route("**/*", handle_route)
