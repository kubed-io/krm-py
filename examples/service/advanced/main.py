"""Advanced example with multiple handlers"""
from flask import request, jsonify


def list_items():
    """GET /api/list"""
    return jsonify({
        "message": "Hello from list!",
        "items": ["item1", "item2", "item3"]
    })


def get_item():
    """GET /api/get?id=123"""
    item_id = request.args.get('id', 'unknown')
    return jsonify({
        "message": "Hello from get!",
        "id": item_id
    })


def create_item():
    """POST /api/create"""
    data = request.get_json() or {}
    return jsonify({
        "message": "Hello from create!",
        "received": data
    }), 201


def delete_item():
    """DELETE /api/delete?id=123"""
    item_id = request.args.get('id', 'unknown')
    return jsonify({
        "message": "Hello from delete!",
        "deleted_id": item_id
    })
