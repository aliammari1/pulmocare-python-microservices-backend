local typedefs = require "kong.db.schema.typedefs"

return {
  name = "body-inspector",
  fields = {
    { consumer = typedefs.no_consumer },
    { protocols = typedefs.protocols_http },
    { config = {
        type = "record",
        fields = {
          { sample_rate = { 
              type = "number", 
              default = 1.0, 
              between = { 0, 1 } 
          }},
          { log_threshold_ms = { 
              type = "number", 
              default = 500 
          }},
        },
      },
    },
  },
}
