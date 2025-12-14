#!/usr/bin/env python
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set


# ------------------------
# 1. Utilidades de parsing
# ------------------------

def load_records(path: Path) -> List[str]:
    """
    Lee un BC3 y devuelve la lista de registros que empiezan por '~'.
    Se asume texto en codificación 'latin-1' (típico de BC3).
    """
    text = path.read_text(encoding="latin-1", errors="replace")
    text = text.replace("\r\n", "\n")

    records: List[str] = []
    i = 0
    n = len(text)

    while True:
        start = text.find("~", i)
        if start == -1:
            break

        end = text.find("|\n", start)
        if end == -1:
            # último registro, puede terminar en '|' sin salto de línea
            last_bar = text.rfind("|")
            if last_bar == -1 or last_bar <= start:
                break
            end = last_bar

        rec = text[start:end]  # sin la barra final
        records.append(rec)
        i = end + 2  # saltamos '|\n'

    return records


def parse_concepts(records: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Parsea los registros ~C (conceptos).
    Devuelve un dict: codigo -> {codigo, unidad, resumen, precio}
    """
    concepts: Dict[str, Dict[str, Any]] = {}

    for rec in records:
        if not rec.startswith("~C|"):
            continue

        fields = rec.split("|")
        if len(fields) < 2:
            continue

        code = fields[1]
        unit = fields[2] if len(fields) > 2 and fields[2] != "" else None
        summary = fields[3] if len(fields) > 3 else ""

        # En muchos BC3 el precio está en el campo 6; si no, 0
        price_str = fields[6] if len(fields) > 6 and fields[6] != "" else "0"
        try:
            price = float(price_str)
        except ValueError:
            price = 0.0

        concepts[code] = {
            "codigo": code,
            "unidad": unit,
            "resumen": summary,
            "precio": price,
        }

    return concepts


def parse_texts(records: List[str]) -> Dict[str, str]:
    """
    Parsea los registros ~T (texto largo).
    Devuelve: codigo -> texto_largo
    """
    texts: Dict[str, str] = {}

    for rec in records:
        if not rec.startswith("~T|"):
            continue

        fields = rec.split("|")
        if len(fields) < 3:
            continue

        code = fields[1]
        # por si hubiera '|' en el texto, juntamos el resto
        long_text = "|".join(fields[2:]).strip()
        texts[code] = long_text

    return texts


def parse_decompositions(records: List[str]) -> Dict[str, List[Tuple[str, float]]]:
    """
    Parsea los registros ~D (descomposición).
    Devuelve: padre -> lista de (hijo, factor)
    """
    decomp: Dict[str, List[Tuple[str, float]]] = {}

    for rec in records:
        if not rec.startswith("~D|"):
            continue

        # ~D|PADRE|BLOQUE_HIJOS
        parts = rec.split("|", 2)
        if len(parts) < 3:
            continue

        parent = parts[1].strip()
        if not parent:
            continue

        children_block = parts[2]
        # En el bloque puede haber varias líneas separadas por '\n'
        lines = children_block.split("\n")
        children: List[Tuple[str, float]] = []

        for line in lines:
            s = line.strip()
            if not s:
                continue

            # las líneas suelen empezar por '|' o '\'
            s = s.lstrip("\\|")
            if not s:
                continue

            segs = s.split("\\")
            if not segs or not segs[0]:
                continue

            code = segs[0]
            factor = 0.0
            if len(segs) > 1 and segs[1]:
                try:
                    factor = float(segs[1])
                except ValueError:
                    factor = 0.0

            children.append((code, factor))

        if children:
            decomp[parent] = children

    return decomp


def parse_measurements(records: List[str]) -> Dict[str, float]:
    """
    Parsea los registros ~M (mediciones) y suma cantidades por código de concepto.
    Devuelve: codigo_concepto -> cantidad_total
    """
    quantities: Dict[str, float] = {}

    for rec in records:
        if not rec.startswith("~M|"):
            continue

        fields = rec.split("|")
        if len(fields) < 3:
            continue

        header = fields[1]
        total_str = fields[-1]

        # header suele ser "PADRE\HIJO" o similar
        parts = header.split("\\")
        # Nos quedamos con el último como código “activo”
        code = parts[-1] or (parts[-2] if len(parts) > 1 else header)

        try:
            total = float(total_str)
        except ValueError:
            continue

        quantities[code] = quantities.get(code, 0.0) + total

    return quantities


# ------------------------
# 2. Construcción del árbol
# ------------------------

def determine_naturaleza(depth: int, has_children: bool) -> int:
    """
    Mapeo de 'naturaleza':
      0 = raíz / obra
      1 = capítulo (hijo directo de raíz, con hijos)
      2 = subcapítulo / nodo intermedio (profundidad >= 2, con hijos)
      3 = partida (sin hijos)
    """
    if depth == 0:
        return 0
    if not has_children:
        return 3
    if depth == 1:
        return 1
    return 2


def build_node(
    code: str,
    depth: int,
    codigo_decimal: str,
    decomp: Dict[str, List[Tuple[str, float]]],
    concepts: Dict[str, Dict[str, Any]],
    texts: Dict[str, str],
    quantities: Dict[str, float],
    visited: Set[str],
) -> Dict[str, Any]:
    """
    Construye recursivamente un nodo del árbol JSON a partir de:
      - code: código BC3 del concepto
      - depth: profundidad en el árbol (0 = raíz)
      - codigo_decimal: ruta jerárquica tipo "01.02.03"
    """
    if code in visited:
        # seguridad ante posibles ciclos raros
        return {}
    visited.add(code)

    concept = concepts.get(code, {})
    unidad = concept.get("unidad")
    resumen = concept.get("resumen", "")
    descripcion_larga = texts.get(code)
    precio = concept.get("precio", 0.0)

    # Hijos según descomposición (necesarios para saber si es capítulo/subcapítulo)
    children_info = decomp.get(code, [])

    # --- CANTIDAD: reglas pedidas ---
    # - raíz (depth 0)                        -> 1
    # - capítulos (depth 1)                   -> 1
    # - subcapítulos (depth >= 2 con hijos)   -> 1
    # - partidas (sin hijos)                  -> cantidad real si hay mediciones, si no 0
    if depth == 0:
        cantidad = 1.0
    elif depth == 1:
        cantidad = 1.0
    elif depth >= 2 and children_info:
        cantidad = 1.0
    else:
        # partida (sin hijos en descomposición)
        if code in quantities:
            cantidad = quantities[code]
        else:
            cantidad = 0.0

    importe = cantidad * precio

    # Construcción recursiva de hijos
    hijos: List[Dict[str, Any]] = []
    for idx, (child_code, factor) in enumerate(children_info, start=1):
        # Generación provisional de codigo_decimal hijo
        if depth == 0:
            child_cd = f"{idx:02d}"
        else:
            child_cd = f"{codigo_decimal}.{idx:02d}"

        child_node = build_node(
            child_code,
            depth + 1,
            child_cd,
            decomp,
            concepts,
            texts,
            quantities,
            visited,
        )
        if child_node:
            hijos.append(child_node)

    naturaleza = determine_naturaleza(depth, bool(hijos or children_info))

    node: Dict[str, Any] = {
        "codigo_decimal": codigo_decimal,  # se renumerará después
        "codigo": code,
        "naturaleza": naturaleza,
        "unidad": unidad,
        "resumen": resumen,
        "descripcion_larga": descripcion_larga,
        "cantidad": cantidad,
        "precio": precio,
        "margen": None,
        "importe": importe,
        "interno": True,  # por defecto siempre True
        "grupo": None,
        "proveedor": None,
        "hijos": hijos,
    }

    return node


def detect_root_code(decomp: Dict[str, List[Tuple[str, float]]]) -> str:
    """
    Detecta el código raíz a partir de las descomposiciones ~D:
    - padres = claves de 'decomp'
    - hijos  = todos los códigos que aparecen como hijo
    - raíz   = padres - hijos
    """
    parents = set(decomp.keys())
    children = {c for chs in decomp.values() for (c, _) in chs}
    roots = parents - children

    if not roots:
        raise RuntimeError("No se ha encontrado ningún nodo raíz en las descomposiciones (~D).")

    if len(roots) == 1:
        return next(iter(roots))

    # Si hubiera más de uno, se podría añadir lógica extra.
    return next(iter(roots))


# ------------------------
# 3. Poda del árbol (eliminar ramas sin partidas del proyecto)
# ------------------------

def _prune_node(node: Dict[str, Any]) -> bool:
    """
    Podamos recursivamente el nodo.
    Devuelve True si ESTE nodo o ALGUNO de sus descendientes
    tiene cantidad > 0. Si no, la rama entera se elimina.

    - Actualiza in-place la lista node["hijos"] con solo las ramas válidas.
    """
    cantidad = node.get("cantidad")
    if isinstance(cantidad, (int, float)):
        cantidad_val = float(cantidad)
    else:
        try:
            cantidad_val = float(cantidad)
        except (TypeError, ValueError):
            cantidad_val = 0.0

    tiene_cantidad = cantidad_val != 0.0

    hijos = node.get("hijos", [])
    hijos_filtrados: List[Dict[str, Any]] = []

    for hijo in hijos:
        if _prune_node(hijo):
            hijos_filtrados.append(hijo)
            tiene_cantidad = True  # un descendiente tiene cantidad > 0

    node["hijos"] = hijos_filtrados
    return tiene_cantidad


def prune_tree(root: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aplica _prune_node a todos los hijos del nodo raíz y
    elimina las ramas que no tienen ninguna partida con cantidad > 0.

    Mantenemos siempre el nodo raíz aunque su cantidad sea 0.
    """
    hijos = root.get("hijos", [])
    hijos_filtrados: List[Dict[str, Any]] = []

    for hijo in hijos:
        if _prune_node(hijo):
            hijos_filtrados.append(hijo)

    root["hijos"] = hijos_filtrados
    return root


# ------------------------
# 4. Re-numeración de codigo_decimal tras la poda
# ------------------------

def _renumber_children(node: Dict[str, Any], depth: int) -> None:
    """
    Renumera recursivamente los hijos de 'node' según el árbol ya podado.

    Regla:
      - raíz: codigo_decimal = "0"
      - hijos de raíz: "01", "02", ...
      - para niveles inferiores: parent.codigo_decimal + ".01", ".02", ...
    """
    hijos = node.get("hijos", [])
    for idx, hijo in enumerate(hijos, start=1):
        if depth == 0:
            cd = f"{idx:02d}"
        else:
            parent_cd = node.get("codigo_decimal", "0")
            cd = f"{parent_cd}.{idx:02d}"

        hijo["codigo_decimal"] = cd
        _renumber_children(hijo, depth + 1)


def renumber_tree(root: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asigna codigo_decimal coherente con la jerarquía LIMPIA (ya podada).
    """
    root["codigo_decimal"] = "0"
    _renumber_children(root, depth=0)
    return root


# ------------------------
# 5. Función principal de conversión
# ------------------------

def bc3_to_json(input_path: Path) -> Dict[str, Any]:
    """
    Convierte un archivo BC3 en un árbol JSON con la estructura:
      - codigo_decimal
      - codigo
      - naturaleza (0,1,2,3)
      - unidad
      - resumen
      - descripcion_larga
      - cantidad
      - precio
      - margen
      - importe
      - interno
      - grupo
      - proveedor
      - hijos: [ ... ]

    Poda los capítulos/subcapítulos sin partidas con cantidad > 0
    y después renumera codigo_decimal según la jerarquía resultante.
    """
    records = load_records(input_path)
    concepts = parse_concepts(records)
    texts = parse_texts(records)
    decomp = parse_decompositions(records)
    quantities = parse_measurements(records)

    root_code = detect_root_code(decomp)

    tree = build_node(
        code=root_code,
        depth=0,
        codigo_decimal="0",
        decomp=decomp,
        concepts=concepts,
        texts=texts,
        quantities=quantities,
        visited=set(),
    )

    # 1) Poda de ramas sin partidas (cantidad = 0 en todo el subárbol)
    tree = prune_tree(tree)

    # 2) Re-numeración de codigo_decimal solo en la estructura ya filtrada
    tree = renumber_tree(tree)

    return tree


# ------------------------
# 6. Gestión del nombre de salida
# ------------------------

def generar_nombre_incremental(path: Path) -> Path:
    """
    Si 'path' no existe, lo devuelve tal cual.
    Si existe, genera nombres tipo:
      fichero.json
      fichero (1).json
      fichero (2).json
    hasta encontrar uno que no exista.
    """
    if not path.exists():
        return path

    carpeta = path.parent
    stem = path.stem      # nombre sin extensión
    suffix = path.suffix  # debería ser .json

    i = 1
    while True:
        nuevo_nombre = f"{stem} ({i}){suffix}"
        nuevo_path = carpeta / nuevo_nombre
        if not nuevo_path.exists():
            return nuevo_path
        i += 1


# ------------------------
# 7. CLI
# ------------------------

def main():
    # Preguntar al usuario la ruta del archivo BC3
    input_path_str = input("Introduce la ruta del archivo BC3: ").strip()
    if not input_path_str:
        print("❌ No se ha introducido ninguna ruta.")
        return

    input_path = Path(input_path_str)

    # Validar que existe
    if not input_path.exists():
        print("❌ El archivo no existe. Comprueba la ruta.")
        return

    # Preguntar el nombre de salida
    output_path_str = input(
        "Introduce el nombre o ruta para guardar el JSON (deja vacío para autogenerar): "
    ).strip()

    if output_path_str:
        output_path = Path(output_path_str)

        # Asegurar extensión .json
        if output_path.suffix.lower() != ".json":
            output_path = output_path.with_suffix(".json")
    else:
        # Autogenerar si está vacío: mismo nombre que el BC3 pero .json
        output_path = input_path.with_suffix(".json")

    # Ajustar para que NO se sobrescriba: generar nombre incremental
    output_path = generar_nombre_incremental(output_path)

    # Ejecutar el parser
    tree = bc3_to_json(input_path)

    # Guardar el archivo
    output_path.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✅ JSON generado en: {output_path}")


if __name__ == "__main__":
    main()
