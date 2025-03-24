local BodyInspectorHandler = {
  PRIORITY = 900,
  VERSION = "1.0.0",
}

-- Function to determine if the request should be logged based on sampling rate
local function should_process_request(conf)
  return math.random() <= conf.sample_rate
end

function BodyInspectorHandler:access(conf)
  if not should_process_request(conf) then
    return
  end
  
  -- Store request data in ngx.ctx for later use
  ngx.ctx.body_inspector = {
    req_body = kong.request.get_raw_body(),
    req_headers = kong.request.get_headers(),
    start_time = ngx.now(),
    service = kong.router.get_service(),
    route = kong.router.get_route()
  }
end

function BodyInspectorHandler:header_filter(conf)
  local ctx = ngx.ctx
  if not ctx.body_inspector then
    return
  end
  
  -- Enable buffering of the response body
  kong.response.set_header("X-Kong-Body-Inspected", "true")
  kong.response.clear_header("Content-Length")
  ngx.header.content_length = nil
end

function BodyInspectorHandler:body_filter(conf)
  local ctx = ngx.ctx
  if not ctx.body_inspector then
    return
  end
  
  local chunk = ngx.arg[1]
  local eof = ngx.arg[2]
  
  if not ctx.body_inspector.resp_body then
    ctx.body_inspector.resp_body = ""
  end
  
  if chunk then
    ctx.body_inspector.resp_body = ctx.body_inspector.resp_body .. chunk
  end
  
  if eof then
    local elapsed = ngx.now() - ctx.body_inspector.start_time
    local status = ngx.status
    
    -- Log to specific endpoint if over threshold
    if conf.log_threshold_ms and elapsed * 1000 > conf.log_threshold_ms then
      local log_data = {
        service = ctx.body_inspector.service and ctx.body_inspector.service.name or "unknown",
        route = ctx.body_inspector.route and ctx.body_inspector.route.name or "unknown",
        request = {
          uri = kong.request.get_path(),
          method = kong.request.get_method(),
          headers = ctx.body_inspector.req_headers,
          body = ctx.body_inspector.req_body,
          query = kong.request.get_query()
        },
        response = {
          status = status,
          headers = kong.response.get_headers(),
          body = ctx.body_inspector.resp_body,
        },
        latency = elapsed * 1000, -- in ms
        timestamp = ngx.time()
      }
      
      kong.log.notice("[body-inspector] Slow request detected: ", kong.json.encode(log_data))
    end
  end
end

return BodyInspectorHandler
