"""drf-spectacular post-processing for the generated client (spec §7, API contract)."""


def response_fields_required(result, generator, request, public):
    """A serializer always writes every field it declares, so in response components every property is present.

    drf-spectacular leaves fields with a model default or ``required=False`` out of ``required``, which makes the
    TypeScript types optional for values the API always sends. Request components (``*Request``, split by
    ``COMPONENT_SPLIT_REQUEST``) keep their own ``required`` list.
    """
    for name, component in result.get("components", {}).get("schemas", {}).items():
        if name.endswith("Request") or component.get("type") != "object" or not component.get("properties"):
            continue
        component["required"] = list(component["properties"])
    return result
