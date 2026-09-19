from rest_framework import status
from rest_framework.exceptions import APIException


class DomainConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested operation conflicts with the current state."
    default_code = "domain_conflict"
