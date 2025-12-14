# BC3 Parser Microservice

A Quarkus-based microservice that parses BC3 construction budget files and returns structured JSON data.

## Overview

This service accepts BC3 files (FIEBDC-3 format) commonly used in the construction industry for budget management, parses them using a Python backend, and returns a hierarchical JSON structure with all budget items, measurements, and decompositions.

## Features

- **RESTful API** for BC3 file upload and parsing
- **Python-based parser** that extracts:
  - Hierarchical budget structure (chapters, subcapters, items)
  - Concepts with codes, units, descriptions, and prices
  - Measurements and quantities
  - Cost decompositions
- **Tree pruning** - removes branches without quantities
- **Automatic code renumbering** based on hierarchy
- **Large file support** (up to 50MB)
- **Virtual threads** for improved concurrency

## API Endpoints

### Parse BC3 File
```bash
POST /parse/bc3
Content-Type: multipart/form-data

curl -X POST -F 'file=@path/to/file.bc3' http://localhost:8080/parse/bc3
```

**Response**: JSON tree structure with:
- `codigo_decimal`: Hierarchical code (e.g., "01.02.03")
- `codigo`: Original BC3 code
- `naturaleza`: Node type (0=root, 1=chapter, 2=subchapter, 3=item)
- `unidad`: Unit of measurement
- `resumen`: Short description
- `descripcion_larga`: Full description
- `cantidad`: Quantity
- `precio`: Unit price
- `importe`: Total amount (cantidad × precio)
- `hijos`: Array of child nodes

### Health Check
```bash
GET /parse/bc3

curl http://localhost:8080/parse/bc3
```

## Running the Service

### Development Mode
```bash
mvn quarkus:dev
```

### Production Build
```bash
mvn package
java -jar target/quarkus-app/quarkus-run.jar
```

## Requirements

- Java 24+
- Python 3.x
- Maven 3.8+

## Configuration

Edit `src/main/resources/application.properties`:

```properties
# Python parser configuration
bc3.parser.python.path=python3
bc3.parser.script.path=src/main/python/parser_wrapper.py
bc3.parser.timeout.seconds=300

# File upload limits
quarkus.http.limits.max-body-size=50M
```

## Technology Stack

- **Quarkus** - Supersonic Subatomic Java Framework
- **RESTEasy Reactive** - JAX-RS implementation
- **Jackson** - JSON processing
- **Python 3** - BC3 parsing logic
