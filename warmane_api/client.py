import asyncio
import copy
import math
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlencode

import httpx


class UpstreamError(Exception):
    def __init__(self, status, code, message, upstream_error=None, retry_after=None):
        self.status = status
        self.code = code
        self.message = message
        self.upstream_error = upstream_error
        self.retry_after = retry_after


class WarmaneClient:
    def __init__(self, http, ttl=60.0, interval=4.0, capacity=256, html_ttl=300.0):
        self.http = http
        self.ttl = ttl
        self.interval = interval
        self.capacity = capacity
        self.html_ttl = html_ttl
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()
        self.lookup_lock = asyncio.Lock()
        self.next_request = 0.0

    async def summary(self, kind, name, realm, wait_for_budget=False):
        path = f"{kind}/{quote_plus(name, safe='')}/{quote_plus(realm, safe='')}/summary"
        return await self._request(path, self._summary, self.ttl, "warmane_json", wait_for_budget=wait_for_budget)

    @staticmethod
    def _summary(response):
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not data["name"]:
            raise ValueError("Expected a resource object with a name")
        return data

    async def page(self, kind, name, realm, section, category=None, wait_for_budget=False):
        from .parsers import parse_page
        path = f"/{kind}/{quote_plus(name, safe='')}/{quote_plus(realm, safe='')}/{section}"
        url = str(self.http.base_url.copy_with(path=path, query=None, fragment=None))
        def decode(response):
            if category is not None:
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get("content"), str):
                    raise ValueError("Expected HTML under content in category response")
                return parse_page(section, body["content"], name, realm, category=category)
            return parse_page(section, response.text, name, realm)
        return await self._request(url, decode, self.html_ttl,
                                   "warmane_ajax_html" if category is not None else "warmane_html",
                                   form={"category": category} if category is not None else None,
                                   wait_for_budget=wait_for_budget)

    async def match(self, name, realm, match_id, wait_for_budget=False):
        from .parsers import match_details
        path = f"/character/{quote_plus(name, safe='')}/{quote_plus(realm, safe='')}/match-history"
        url = str(self.http.base_url.copy_with(path=path, query=None, fragment=None))
        return await self._request(url, lambda response: match_details(response.json(), name, realm),
                                   self.html_ttl, "warmane_ajax_json", form={"matchinfo": str(match_id)},
                                   wait_for_budget=wait_for_budget)

    async def _request(self, path, decode, ttl, source, form=None, wait_for_budget=False):
        key = path if form is None else path + "?" + urlencode(sorted(form.items()))
        cached = self.cache.get(key)
        if cached and cached[0] > time.monotonic():
            self.cache.move_to_end(key)
            return copy.deepcopy(cached[1]), {**cached[2], "cached": True}
        # One in-flight request; fail fast instead of allowing unbounded queues.
        if not wait_for_budget and (self.lock.locked() or time.monotonic() < self.next_request):
            retry = max(1, math.ceil(self.next_request - time.monotonic()))
            raise UpstreamError(503, "upstream_cooldown", "Upstream request budget is busy; retry later.", retry_after=retry)
        async with self.lock:
            # A combined lookup waits its turn, then rechecks the cache in case
            # another request fetched this source while it was waiting.
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                self.cache.move_to_end(key)
                return copy.deepcopy(cached[1]), {**cached[2], "cached": True}
            delay = self.next_request - time.monotonic()
            if delay > 0:
                if delay > self.interval:
                    raise UpstreamError(503, "upstream_cooldown", "Warmane is cooling down; retry later.", retry_after=math.ceil(delay))
                await asyncio.sleep(delay)
            self.next_request = time.monotonic() + self.interval
            try:
                response = await self.http.request("POST" if form else "GET", path, data=form,
                    headers={"X-Requested-With": "XMLHttpRequest"} if form else None)
            except httpx.TimeoutException as exc:
                raise UpstreamError(504, "upstream_timeout", "Warmane did not respond in time.") from exc
            except httpx.RequestError as exc:
                raise UpstreamError(502, "upstream_unavailable", "Could not reach Warmane.") from exc
            if response.status_code == 429:
                retry = 60
                header = response.headers.get("retry-after", "")
                if header.isdigit():
                    retry = max(1, int(header))
                elif header:
                    try:
                        retry = max(1, math.ceil((parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()))
                    except (ValueError, TypeError, OverflowError):
                        pass
                self.next_request = time.monotonic() + retry
                raise UpstreamError(503, "upstream_rate_limited", "Warmane rate limited this server.", retry_after=retry)
            if response.status_code == 404:
                raise UpstreamError(404, "not_found", "Warmane returned HTTP 404.")
            if not response.is_success:
                raise UpstreamError(502, "upstream_http_error", f"Warmane returned HTTP {response.status_code}.")
            try:
                error_body = response.json()
            except ValueError:
                error_body = None
            if isinstance(error_body, dict) and "error" in error_body:
                # Warmane's numeric error codes are undocumented; do not guess meanings.
                self.next_request = time.monotonic() + max(60, self.interval)
                raise UpstreamError(502, "upstream_api_error", "Warmane returned an API error.", error_body["error"], math.ceil(max(60, self.interval)))
            try:
                data = await asyncio.to_thread(decode, response)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
                raise UpstreamError(502, "invalid_upstream_response", "Warmane response did not match the expected structure.") from exc
            meta = {"cached": False, "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "cache_ttl_seconds": ttl, "source": source, "source_url": str(response.url)}
            if form:
                meta["source_parameters"] = form.copy()
                if "category" in form:
                    meta["source_category"] = str(form["category"])
            self.cache[key] = (time.monotonic() + ttl, copy.deepcopy(data), meta)
            self.cache.move_to_end(key)
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            return data, dict(meta)
