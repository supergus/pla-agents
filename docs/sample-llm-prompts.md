# Sample prompts: what the system sends to the LLM

The prompts live in `supergus/rfq-demo` (`worker/src/prompts/`); this is a rendered snapshot as of 2026-11-04.

The Worker (`worker/src/ai.js`) sends each step as two chat messages (system and user) with a JSON schema that forces the reply format. These are the exact prompts and schemas from `worker/src/prompts/` on `main`, rendered with sample inputs.

Inputs: the parse step gets the RFQ-1003 sample email exactly as the demo sends it. The match input is exactly what the demo sends. For explain_quote the dollar figures are **illustrative** (the BRK-100 worked-example prices); the demo fills in the actual computed quote of the current run. The model never calculates: after the reply, the tool code rejects any number that isn't in the input.

## 1. parse_rfq_document

### Request sent to Llama 3.3 70B

```
model: @cf/meta/llama-3.3-70b-instruct-fp8-fast
max_tokens: 1024 (cap)
response_format: json_schema (schema below)
```

**Message 1, role `system`:**

```text
You extract a manufacturing RFQ (request for quote) into JSON.
Rules: copy values from the text; use "" for anything not stated; never guess.
rfq_id: the RFQ number, e.g. RFQ-1003. revision: letter/number only, e.g. A.
lines: one per part. quantities: EVERY quantity or volume break requested for that part, as integers ("2,500" -> 2500).
incoterm: one of EXW,FCA,FOB,CIF,DAP,DDP or "". delivery_date: YYYY-MM-DD or "".
confidence: 0..1 per field; use below 0.7 when the text is tentative (e.g. a question mark or 'will confirm').
ambiguities: short notes on anything tentative or unclear.
```

**Message 2, role `user`:**

```text
RFQ text:
From: purchasing@northwind.example
Subject: RFQ-1003 rev A - BRK-300 welded bracket

Hello,

Please quote RFQ-1003 rev A for the BRK-300 welded mounting bracket per drawing BRK-300 rev A.
Material: ASTM A36 steel plate. Quantities: 250 and 2,500 pieces.
Delivery by 1 April 2027. Payment Net 30. We'd normally want it delivered to our dock (DAP?) but
logistics will confirm.

Thanks,
Northwind Agricultural Equipment

```

**JSON schema the reply must follow:**

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "rfq_id",
    "revision",
    "customer",
    "payment_terms",
    "incoterm",
    "delivery_date",
    "drawing",
    "material_spec",
    "finish_spec",
    "lines",
    "confidence",
    "ambiguities"
  ],
  "properties": {
    "rfq_id": {
      "type": "string"
    },
    "revision": {
      "type": "string"
    },
    "customer": {
      "type": "string"
    },
    "payment_terms": {
      "type": "string"
    },
    "incoterm": {
      "type": "string"
    },
    "delivery_date": {
      "type": "string"
    },
    "drawing": {
      "type": "string"
    },
    "material_spec": {
      "type": "string"
    },
    "finish_spec": {
      "type": "string"
    },
    "lines": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "part",
          "description",
          "quantities"
        ],
        "properties": {
          "part": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "quantities": {
            "type": "array",
            "items": {
              "type": "integer"
            }
          }
        }
      }
    },
    "confidence": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "customer",
        "incoterm",
        "delivery_date",
        "material_spec",
        "lines"
      ],
      "properties": {
        "customer": {
          "type": "number"
        },
        "incoterm": {
          "type": "number"
        },
        "delivery_date": {
          "type": "number"
        },
        "material_spec": {
          "type": "number"
        },
        "lines": {
          "type": "number"
        }
      }
    },
    "ambiguities": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  }
}
```

After the reply, code checks that the structure is valid and that every quantity appears in the email text. If not, the step throws and the workflow retries.

## 2. match_library_part

### Request sent to Llama 3.3 70B

```
model: @cf/meta/llama-3.3-70b-instruct-fp8-fast
max_tokens: 1024 (cap)
response_format: json_schema (schema below)
```

**Message 1, role `system`:**

```text
Match the requested RFQ line to the most similar known product.
Choose product_id ONLY from the candidate ids given, or "NONE" if no candidate is a reasonable match.
score: similarity 0..1. method: short name of how you judged (e.g. llm-similarity: family+process).
rationale: one sentence.
```

**Message 2, role `user`:**

```text
{"line":"RFQ-1002 line 1: BRK-200 welded mounting bracket","requirements":["ASTM A36 steel plate"],"candidates":{"BRK-100":"BRK-100 welded mounting bracket"}}
```

**JSON schema the reply must follow:**

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "product_id",
    "score",
    "method",
    "rationale"
  ],
  "properties": {
    "product_id": {
      "type": "string"
    },
    "score": {
      "type": "number"
    },
    "method": {
      "type": "string"
    },
    "rationale": {
      "type": "string"
    }
  }
}
```

After the reply, code checks that `product_id` is one of the candidate ids (or `NONE`) and that the score is between 0 and 1. A score below 0.8 means a human must confirm the match.

## 3. explain_quote

### Request sent to Llama 3.3 70B

```
model: @cf/meta/llama-3.3-70b-instruct-fp8-fast
max_tokens: 1024 (cap)
response_format: json_schema (schema below)
```

**Message 1, role `system`:**

```text
You explain a computed manufacturing quote in plain language for a customer and a reviewer.
Use ONLY numbers that appear in the input, written exactly as given; never calculate, round or invent numbers.
summary: 2-3 sentences. drivers: 2-4 short cost drivers. breaks: one short sentence per quantity break.
caveats: short notes (may be empty).
```

**Message 2, role `user`:**

```text
Quote:
{"quote":"Q-1002-A","product":"BRK-200 bracket (priced as BRK-100)","incoterm":"DAP","breaks":[{"line":"L1","quantity":100,"unit_price":60.86,"nre":1850,"freight":0.8,"total":8016},{"line":"L1","quantity":1000,"unit_price":58.01,"nre":1850,"freight":0.8,"total":60660},{"line":"L1","quantity":10000,"unit_price":57.72,"nre":1850,"freight":0.8,"total":587050}]}
```

**JSON schema the reply must follow:**

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "summary",
    "drivers",
    "breaks",
    "caveats"
  ],
  "properties": {
    "summary": {
      "type": "string"
    },
    "drivers": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "breaks": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "caveats": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  }
}
```

After the reply, code checks that every number in the text appears in the input.
