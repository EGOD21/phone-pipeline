from __future__ import annotations

import hashlib
import html.parser
import json
import urllib.parse
import urllib.request

from smb_phone_pipeline.config import Settings
from smb_phone_pipeline.models import RawBusiness, SearchPartition
from smb_phone_pipeline.providers.base import BusinessProvider


class YellowPagesApiProvider(BusinessProvider):
    source_name = "yellowpages_authorized_api"

    def __init__(self, settings: Settings):
        if not settings.yp_api_base_url:
            raise ValueError("YP_API_BASE_URL is required for yp-api source")
        self.settings = settings

    def fetch_partition(self, partition: SearchPartition) -> list[RawBusiness]:
        host = urllib.parse.urlparse(self.settings.yp_api_base_url).netloc
        if host.endswith("rapidapi.com"):
            query = urllib.parse.urlencode(
                {
                    "search_terms": partition.category,
                    "geo_location_terms": f"{partition.city}, {partition.state}",
                    "page": partition.page,
                }
            )
        else:
            query = urllib.parse.urlencode(
                {
                    "category": partition.category,
                    "city": partition.city,
                    "state": partition.state,
                    "page": partition.page,
                }
            )
        url = f"{self.settings.yp_api_base_url}?{query}"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.settings.yp_api_key and host.endswith("rapidapi.com"):
            headers["x-rapidapi-key"] = self.settings.yp_api_key
            headers["x-rapidapi-host"] = host
        elif self.settings.yp_api_key:
            headers["Authorization"] = f"Bearer {self.settings.yp_api_key}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(
            request, timeout=self.settings.yp_api_timeout_seconds
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("businesses") or payload.get("results") or payload.get("data") or []
        else:
            rows = []
        if not isinstance(rows, list):
            raise ValueError("YP API response must be a list or contain businesses/results/data list")
        return [_raw_from_payload(self.source_name, row, url) for row in rows]


class YellowPagesAuthorizedScraperProvider(BusinessProvider):
    source_name = "yellowpages_authorized_scraper"

    def __init__(self, settings: Settings):
        if not settings.yp_authorizes_automated_extraction:
            raise ValueError(
                "YP_AUTHORIZES_AUTOMATED_EXTRACTION=true is required for yp-scraper source"
            )
        if not settings.yp_search_url_template:
            raise ValueError("YP_SEARCH_URL_TEMPLATE is required for yp-scraper source")
        self.settings = settings

    def fetch_partition(self, partition: SearchPartition) -> list[RawBusiness]:
        url = self.settings.yp_search_url_template.format(
            category=urllib.parse.quote(partition.category),
            city=urllib.parse.quote(partition.city),
            state=urllib.parse.quote(partition.state),
            page=partition.page,
        )
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AuthorizedSMBPhonePipeline/0.1 (+written-authorization-required)"
            },
        )
        with urllib.request.urlopen(
            request, timeout=self.settings.yp_api_timeout_seconds
        ) as response:
            html = response.read().decode("utf-8", errors="replace")
        parser = JsonLdBusinessParser()
        parser.feed(html)
        return [_raw_from_payload(self.source_name, row, url) for row in parser.businesses]


class JsonLdBusinessParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_jsonld = False
        self._chunks: list[str] = []
        self.businesses: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        self._in_jsonld = attr_map.get("type", "").lower() == "application/ld+json"
        if self._in_jsonld:
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._in_jsonld:
            return
        self._in_jsonld = False
        raw = "".join(self._chunks).strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        for item in _flatten_jsonld(payload):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(t in {"LocalBusiness", "Store", "ProfessionalService"} for t in types):
                address = item.get("address") if isinstance(item.get("address"), dict) else {}
                self.businesses.append(
                    {
                        "name": item.get("name"),
                        "phone": item.get("telephone"),
                        "website": item.get("url"),
                        "address1": address.get("streetAddress"),
                        "city": address.get("addressLocality"),
                        "state": address.get("addressRegion"),
                        "postal_code": address.get("postalCode"),
                        "category": item.get("@type"),
                    }
                )


def _flatten_jsonld(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for child in payload for item in _flatten_jsonld(child)]
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for child in graph for item in _flatten_jsonld(child)]
        return [payload]
    return []


def _raw_from_payload(source: str, row: dict, source_url: str) -> RawBusiness:
    source_ref = str(
        row.get("id")
        or row.get("listing_id")
        or row.get("source_ref")
        or hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
    )
    return RawBusiness(
        source=source,
        source_ref=source_ref,
        source_url=source_url,
        raw_payload=row,
    )
