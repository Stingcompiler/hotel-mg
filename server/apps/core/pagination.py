"""List pagination (spec §7): ``?page&page_size``, default 50, capped."""

from rest_framework.pagination import PageNumberPagination


class Pagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
