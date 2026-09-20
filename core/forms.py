"""Đưa lỗi nghiệp vụ về form, kể cả khi form không chứa trường của model."""


def add_service_errors(form, error):
    if hasattr(error, "error_dict"):
        for field, errors in error.error_dict.items():
            form.add_error(field if field in form.fields else None, errors)
    else:
        form.add_error(None, error)


def filter_query_string(params):
    query = params.copy()
    query.pop("page", None)
    return query.urlencode()
