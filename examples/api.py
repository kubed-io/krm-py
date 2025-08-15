#!/usr/bin/env python3

# this: https://python-jsonschema.readthedocs.io/en/stable/faq/#why-doesn-t-my-schema-s-default-property-set-the-default-on-my-instance
import json
import jsonschema
from jsonschema import validate, Draft7Validator, validators

# A sample schema
schema = {
    "type": "object",
    "required": [
       "name"
    ],
    "properties": {
        "name": {
            "type": "string"
        },
        "age": {
            "type": "integer",
            "format": "int32",
            "minimum": 0,
            "nullable": True,
        },
        "birth-date": {
            "type": "string",
            "format": "date",
        },
        "food": {
            "type": "string",
            "default": "pizza"
        },
        "getup": {
            "type": "object",
            "default": {},
            "properties": {
                "hat": {
                    "type": "boolean",
                    "default": True
                },
                "tie": {
                    "type": "boolean",
                    "default": False
                }
            }
        }
    },
    "additionalProperties": False,
}

obj = {"name": "John", "age": 23}

def extend_with_default(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, subschema["default"])

        for error in validate_properties(
            validator, properties, instance, schema,
        ):
            yield error

    return validators.extend(
        validator_class, {"properties" : set_defaults},
    )

DefaultValidatingDraft7Validator = extend_with_default(Draft7Validator)

DefaultValidatingDraft7Validator(schema).validate(obj)

print(obj)

# def validate_obj(obj):
#     try:
#         obj = validate(instance=obj, schema=schema)
#         print(obj)
#     except jsonschema.exceptions.ValidationError as error:
#         return False
#     return True

# validate_obj(someone)
