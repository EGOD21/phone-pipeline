from __future__ import annotations

from abc import ABC, abstractmethod

from smb_phone_pipeline.models import RawBusiness, SearchPartition


class BusinessProvider(ABC):
    source_name: str

    @abstractmethod
    def fetch_partition(self, partition: SearchPartition) -> list[RawBusiness]:
        raise NotImplementedError
