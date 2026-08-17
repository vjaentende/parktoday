"""Cliente Python para la API de datos.gob.es (catálogo nacional de datos abiertos)."""

from __future__ import annotations

from typing import Any, Generator

import httpx

BASE_URL = "https://datos.gob.es/apidata"
MAX_PAGE_SIZE = 50
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3


class DatosGobError(Exception):
    """Error en una petición a datos.gob.es."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class DatosGobClient:
    """Cliente para la API REST de datos.gob.es."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        transport = httpx.HTTPTransport(retries=retries)
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    # -- internal -------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Hace GET, valida status y devuelve el JSON completo."""
        response = self._client.get(path, params=params)
        if response.status_code != 200:
            raise DatosGobError(response.status_code, response.text[:300])
        return response.json()

    def _result(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Devuelve solo el campo 'result' de la respuesta."""
        return self._get(path, params)["result"]

    # -- datasets -------------------------------------------------------------

    def list_datasets(
        self, page: int = 0, page_size: int = MAX_PAGE_SIZE, sort: str | None = None
    ) -> dict[str, Any]:
        """Lista datasets con paginación."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        if sort:
            params["_sort"] = sort
        return self._result("/catalog/dataset", params)

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        """Obtiene un dataset por su id."""
        return self._result(f"/catalog/dataset/{dataset_id}")

    def search_datasets_by_title(
        self, text: str, page: int = 0, page_size: int = MAX_PAGE_SIZE
    ) -> dict[str, Any]:
        """Busca datasets cuyo título contenga *text*."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        return self._result(f"/catalog/dataset/title/{text}", params)

    def datasets_by_publisher(
        self, publisher_id: str, page: int = 0, page_size: int = MAX_PAGE_SIZE
    ) -> dict[str, Any]:
        """Datasets publicados por un organismo."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        return self._result(f"/catalog/dataset/publisher/{publisher_id}", params)

    def datasets_by_spatial(
        self, kind: str, value: str, page: int = 0, page_size: int = MAX_PAGE_SIZE
    ) -> dict[str, Any]:
        """Datasets por cobertura geográfica (ej. kind='Autonomia', value='Cataluna')."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        return self._result(f"/catalog/dataset/spatial/{kind}/{value}", params)

    def datasets_by_theme(
        self, theme: str, page: int = 0, page_size: int = MAX_PAGE_SIZE
    ) -> dict[str, Any]:
        """Datasets por sector/tema NTI (ej. 'sector-publico')."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        return self._result(f"/catalog/dataset/theme/{theme}", params)

    # -- distributions --------------------------------------------------------

    def list_distributions(
        self, page: int = 0, page_size: int = MAX_PAGE_SIZE
    ) -> dict[str, Any]:
        """Lista distribuciones (ficheros descargables)."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        return self._result("/catalog/distribution", params)

    # -- publishers -----------------------------------------------------------

    def list_publishers(
        self, page: int = 0, page_size: int = MAX_PAGE_SIZE
    ) -> dict[str, Any]:
        """Lista publicadores."""
        params: dict[str, Any] = {"_page": page, "_pageSize": min(page_size, MAX_PAGE_SIZE)}
        return self._result("/catalog/publisher", params)

    # -- iterador paginado ----------------------------------------------------

    def iter_datasets(
        self, page_size: int = MAX_PAGE_SIZE, sort: str | None = None
    ) -> Generator[dict[str, Any], None, None]:
        """Generador que itera sobre TODOS los datasets paginando automáticamente."""
        page = 0
        size = min(page_size, MAX_PAGE_SIZE)
        while True:
            result = self.list_datasets(page=page, page_size=size, sort=sort)
            items = result.get("items", [])
            yield from items
            if "next" not in result or not items:
                break
            page += 1

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DatosGobClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Ejemplos
# ---------------------------------------------------------------------------

def _get_title(dataset: dict[str, Any]) -> str:
    """Extrae el título en español de un dataset."""
    title = dataset.get("title", "")
    if isinstance(title, list):
        for t in title:
            if isinstance(t, dict) and t.get("_lang") == "es":
                return t["_value"]
        return title[0]["_value"] if title else "(sin título)"
    return str(title)


if __name__ == "__main__":
    with DatosGobClient() as client:
        # 1) Buscar datasets por título
        print("=== Buscar datasets con 'aparcamiento' en el título ===")
        result = client.search_datasets_by_title("aparcamiento", page_size=5)
        for ds in result.get("items", []):
            print(f"  - {_get_title(ds)}")

        # 2) Listar una página de datasets
        print("\n=== Primera página de datasets (3 resultados) ===")
        result = client.list_datasets(page_size=3)
        for ds in result.get("items", []):
            print(f"  - {_get_title(ds)}")

        # 3) Iterar los primeros 10 datasets con el generador
        print("\n=== Primeros 10 datasets (iter_datasets) ===")
        for i, ds in enumerate(client.iter_datasets(page_size=5)):
            if i >= 10:
                break
            print(f"  {i + 1}. {_get_title(ds)}")
