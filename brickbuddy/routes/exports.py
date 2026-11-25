"""Fichiers d'export BrickLink et BrickOwl."""
from .. import exports
from ..flask_app import app
from flask import Response
import csv
import io
import xml.etree.ElementTree as ET

@app.get("/export/bricklink.xml")
def export_bricklink():
    quantities = exports.get_export_quantities(exports.export_scope())
    root = ET.Element("INVENTORY")
    for (part_num, color_id), quantity in quantities.items():
        item = ET.SubElement(root, "ITEM")
        for tag, value in (
            ("ITEMTYPE", "P"),
            ("ITEMID", part_num),
            ("COLOR", color_id),
            ("MINQTY", quantity),
        ):
            ET.SubElement(item, tag).text = str(value)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(payload, mimetype="application/xml", headers={"Content-Disposition": "attachment; filename=legolist-bricklink.xml"})



@app.get("/export/brickowl.csv")
def export_brickowl():
    quantities = exports.get_export_quantities(exports.export_scope())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["ItemNo", "Color", "Qty"])
    for (part_num, color_id), quantity in quantities.items():
        writer.writerow([part_num, color_id, quantity])
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=legolist-brickowl.csv"},
    )
