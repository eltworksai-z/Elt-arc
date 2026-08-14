L2 CDM Canonical Model and Metadata/API Architecture
1. Purpose
This document captures the architecture discussion around:
Databricks metadata and ERD representation
REST API versus ERD/data model
How API JSON relates to relational metadata
L1 CDM and L2 CDM Canonical
Canonical JSON sent through Kafka
Separate Kafka and batch consumers
Whether L2 should be one canonical JSON or multiple normalized JSONs
Recommended terminology and final architecture decision
2. Databricks example: ERD versus REST API
The Databricks Information Schema documentation shows a relational metadata model containing entities such as:
CATALOGS
SCHEMATA
TABLES
COLUMNS
SCHEMA_PRIVILEGES
etc.
This is an ERD/data model representation. It describes metadata relations, columns, keys, and relationships.
For example:
CATALOG
   |
   | 1
   |
SCHEMATA
   |
   | 1
   |
   | *
   v
TABLES
   |
   | 1
   |
   | *
   v
COLUMNS
Databricks documents SCHEMATA as describing schemas within a catalog. Its logical primary key is CATALOG_NAME + SCHEMA_NAME.
TABLES uses TABLE_CATALOG + TABLE_SCHEMA as the foreign-key relationship back to SCHEMATA.
Therefore:
SCHEMATA
PK: CATALOG_NAME, SCHEMA_NAME

        1
        |
        | 
        | *
        v

TABLES
FK: TABLE_CATALOG, TABLE_SCHEMA
PK: TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME
The important point is that the ERD is describing the relational metadata model, not necessarily the JSON contract of a REST API.
3. What happens when a REST API is called?
A REST API is an interface through which an application retrieves or modifies metadata.
For example, Databricks provides a Get Schema REST API conceptually like:
GET /api/2.1/unity-catalog/schemas/{full_name}
The API returns a JSON object containing fields such as:
{
  "catalog_name": "prod",
  "full_name": "prod.sales",
  "name": "sales",
  "owner": "admin",
  "schema_id": "..."
}
Notice that these names do not have to be identical to Information Schema column names.
For example:
Information Schema       REST API
------------------       --------
SCHEMA_NAME              name
SCHEMA_OWNER             owner
CATALOG_NAME             catalog_name
This is normal.
The REST API has its own API response contract. The backend can map internal/relational metadata into that contract.
Therefore:
ERD/data model != REST API contract
The ERD and REST API may represent the same underlying business/technical metadata, but they can expose it differently.
4. Three different representations
It is useful to separate three concepts:
1. Internal / relational metadata model
        |
        v
2. REST API representation
        |
        v
3. Consumer/application representation
Example:
Relational model:

SCHEMATA
  CATALOG_NAME
  SCHEMA_NAME
  SCHEMA_OWNER


REST API:

{
  "catalog_name": "prod",
  "name": "sales",
  "owner": "admin"
}


Application canonical model:

{
  "catalog": "prod",
  "schema": {
    "name": "sales",
    "owner": "admin"
  }
}
There is no requirement that all three representations use identical field names or structures.
5. Foreign-key relationships in JSON
A relational database explicitly defines relationships using keys.
Example:
SCHEMATA
---------------------
CATALOG_NAME
SCHEMA_NAME
and:
TABLES
---------------------
TABLE_CATALOG
TABLE_SCHEMA
TABLE_NAME
The relational relationship is:
TABLES.TABLE_CATALOG + TABLES.TABLE_SCHEMA
        |
        v
SCHEMATA.CATALOG_NAME + SCHEMATA.SCHEMA_NAME
A JSON representation does not need to explicitly say:
{
  "foreign_key": "SCHEMATA.SCHEMA_NAME"
}
The relationship can instead be represented structurally:
{
  "schema_name": "sales",
  "tables": [
    {
      "table_name": "customers"
    },
    {
      "table_name": "orders"
    }
  ]
}
Here, the nesting itself communicates that the tables belong to the sales schema.
However, identifiers such as catalog, schema, table, and entity IDs should still be retained where they are needed for traceability, correlation, reconciliation, or downstream processing.
6. Important distinction: logical model versus physical model
A logical/canonical model describes what the business object means.
A physical model describes how the data is stored or transported in a particular implementation.
Example canonical business object:
{
  "entity": {
    "id": "E123",
    "name": "ABC"
  },
  "registration": {
    "id": "R456"
  },
  "organization": {
    "id": "O789"
  },
  "relationships": [
    {
      "from": "E123",
      "to": "O789",
      "type": "REGISTERED_BY"
    }
  ]
}
A physical relational representation could be:
ENTITY
------
entity_id
name

REGISTRATION
------------
registration_id
entity_id

ORGANIZATION
------------
organization_id
name

ENTITY_RELATIONSHIP
-------------------
from_entity_id
to_entity_id
relationship_type
These are two representations of the same business information.
They should not automatically be treated as the same model.
7. Proposed biologics entity registration architecture
The use case is a biologics entity registration flow.
The proposed conceptual flow is:
Source Event
     |
     v
L1 CDM
     |
     v
L2 CDM Canonical
     |
     v
Canonical JSON
     |
     +----------------------+
     |                      |
     v                      v
   Kafka                  Batch
     |                      |
     v                      v
Other Application       Batch Consumer
     |                      |
additional processing       v
                      Batch CDM / tables
The key architectural point is:
Kafka and Batch are separate consumers of the L2 canonical representation.
The batch process is NOT consuming Kafka and then creating the batch model.
Instead:
L2 Canonical
   |
   +----> Kafka ---> Other Application
   |
   +----> Batch ---> Batch CDM
8. What does L2 CDM Canonical mean?
In this architecture:
L2 CDM Canonical = the agreed canonical business representation of a biologics entity registration.
Canonical does not mean "end-user JSON".
Canonical means:
The organization has agreed on one standard representation of the business object, independent of the source system or downstream implementation.
For example:
Biologics Entity Registration
        |
        +-- Entity
        +-- Registration
        +-- Organization
        +-- Product
        +-- Relationships
The canonical representation can be serialized as one JSON event.
9. Why one canonical JSON is a reasonable design
Suppose the business event is:
Biologics Entity Registration
and the event contains related information:
Entity
Registration
Organization
Product
Relationships
A canonical JSON can preserve the complete business context:
{
  "entity": {
    "id": "E123",
    "name": "ABC"
  },
  "registration": {
    "id": "R456",
    "country": "US"
  },
  "organization": {
    "id": "O789",
    "name": "ABC Pharma"
  },
  "products": [
    {
      "id": "P001",
      "name": "Product A"
    }
  ],
  "relationships": [
    {
      "from": "E123",
      "to": "O789",
      "type": "REGISTERED_BY"
    }
  ]
}
This preserves the business transaction/context as one canonical object.
That object can then be consumed independently by different downstream systems.
10. Alternative: multiple normalized JSON messages
Another design would split the same business object into multiple JSON messages:
Entity JSON
Registration JSON
Organization JSON
Product JSON
Relationship JSON
This can be useful when each entity is independently owned, processed, scaled, or consumed.
However, it introduces additional concerns for a consumer that needs the complete business registration:
correlation IDs
message ordering
partial arrival
duplicate handling
reconstruction of relationships
state management
eventual consistency
additional joins/reassembly
The decision therefore should not be made simply because the underlying data model is relational.
11. Recommended separation of concerns
The cleanest architectural separation is:
L1 CDM
  ↓
L2 CDM Canonical
  ↓
Canonical business event
  ↓
Canonical JSON
  ↓
+---------------------+
|                     |
v                     v
Kafka                 Batch
|                     |
v                     v
Other application     Batch CDM
The canonical model defines the business meaning.
The Kafka JSON defines the event serialization/transport representation.
The Batch CDM defines the batch consumer's physical/analytical representation.
These should not automatically be forced to have identical structures.
12. Why the L2 naming can become confusing
If the organization uses the term:
L2 CDM
for the canonical streaming/business representation, then it is better not to also call the downstream normalized batch tables "L2 CDM".
Otherwise people may interpret:
L2 CDM = canonical event
and:
L2 CDM = normalized batch tables
as the same thing.
A clearer terminology is:
L1 CDM
    ↓
L2 CDM Canonical
    ↓
Canonical Event / Canonical JSON
    ↓
    +----------------+
    |                |
    v                v
 Kafka             Batch
    |                |
    v                v
Other App        Batch CDM
If the organization has an existing formal definition of "L2 CDM", that definition should take precedence. The terminology should be agreed before deciding the serialization structure.
13. Final architectural position
The recommended decision is not simply "one JSON is better than multiple JSONs."
The stronger architectural position is:
Define L2 CDM as the canonical business representation of the biologics entity registration. Preserve the business entity and its required relationships within that canonical representation. Serialize it as a canonical JSON event where Kafka requires JSON. Allow each downstream consumer, including the batch consumer, to transform the canonical representation into its own physical/analytical model.
In short:
Canonical model
      ≠
Physical storage model
and:
ERD
      ≠
REST API contract
      ≠
Canonical JSON
      ≠
Batch CDM
They can represent related information while serving different purposes.
14. Decision tree
Use one canonical JSON when:
the business event has a clear transaction/business boundary
consumers need the related entities together
the relationships are part of the event context
Kafka is carrying a business event rather than independent entity changes
downstream consumers can independently transform the canonical event
Consider multiple messages when:
entities are independently produced/owned
each entity has its own lifecycle
consumers independently subscribe to each entity type
payload size becomes a concern
independent replay/scaling is important
the business explicitly defines separate events
The most important question is:
What is the business/event boundary of an L2 CDM message?
If the answer is "one biologics entity registration", a single canonical event containing the relevant related context is a strong candidate.
15. Databricks example used to explain the concept
Databricks Unity Catalog provides a useful example of why the representations should not be confused.
Information Schema
Databricks exposes relational metadata through Information Schema relations such as SCHEMATA and TABLES.
For example:
SCHEMATA
  CATALOG_NAME
  SCHEMA_NAME
  SCHEMA_OWNER

TABLES
  TABLE_CATALOG
  TABLE_SCHEMA
  TABLE_NAME
The relationship is:
SCHEMATA
   1
   |
   | *
   v
TABLES
REST API
Databricks separately exposes Unity Catalog metadata through REST APIs.
For example:
GET /api/2.1/unity-catalog/schemas/{full_name}
The response has its own JSON contract, with fields such as:
catalog_name
full_name
name
owner
schema_id
properties
...
Therefore it is expected that:
SCHEMA_NAME
in Information Schema does not necessarily appear as:
SCHEMA_NAME
in the REST response. It may appear as:
name
The API contract is a separate representation.
16. Key takeaway
The central architecture principle is:
Source
  ↓
L1 CDM
  ↓
L2 CDM Canonical
  ↓
Canonical JSON
  ↓
  ├──────── Kafka → Other Application
  │
  └──────── Batch → Batch CDM
Do not derive the event design directly from the physical relational ERD.
Instead:
Define the business meaning of the L2 CDM.
Define the canonical entity and relationship structure.
Define the canonical event boundary.
Serialize that canonical object into JSON if required by Kafka.
Let downstream applications transform it into their own physical models.
This keeps business semantics, transport format, and physical persistence concerns separate.
Official Databricks references
Databricks SCHEMATA Information Schema: https://docs.databricks.com/aws/en/sql/language-manual/information-schema/schemata
Databricks TABLES Information Schema: https://docs.databricks.com/aws/en/sql/language-manual/information-schema/tables
Databricks Get Schema REST API: https://docs.databricks.com/api/azure/workspace/schemas/get
Databricks List Schemas REST API: https://docs.databricks.com/api/workspace/schemas/list
