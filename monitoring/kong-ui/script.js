document.addEventListener('DOMContentLoaded', function() {
    // Configuration
    const ELASTICSEARCH_ENDPOINT = '/es/kong-logs-*/_search';
    const REFRESH_INTERVAL = 5000; // 5 seconds
    
    // State
    let services = new Set();
    let currentRequests = [];
    
    // Load initial data
    fetchRequests();
    
    // Set up auto-refresh
    setInterval(fetchRequests, REFRESH_INTERVAL);
    
    // Set up event listeners for filters
    document.getElementById('serviceFilter').addEventListener('change', applyFilters);
    document.getElementById('statusFilter').addEventListener('change', applyFilters);
    document.getElementById('methodFilter').addEventListener('change', applyFilters);
    document.getElementById('searchFilter').addEventListener('input', applyFilters);
    
    function fetchRequests() {
        const query = {
            size: 100,
            sort: [
                { "@timestamp": { order: "desc" } }
            ],
            query: {
                bool: {
                    must: [
                        { exists: { field: "request_body" } },
                        { exists: { field: "response_body" } }
                    ]
                }
            }
        };
        
        fetch(ELASTICSEARCH_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(query)
        })
        .then(response => response.json())
        .then(data => {
            processRequests(data.hits.hits);
        })
        .catch(error => {
            console.error('Error fetching requests:', error);
            document.getElementById('requests-container').innerHTML = `
                <div class="alert alert-danger">
                    Error loading requests. Please check the console for details.
                </div>
            `;
        });
    }
    
    function processRequests(hits) {
        currentRequests = hits.map(hit => {
            const source = hit._source;
            return {
                id: hit._id,
                timestamp: new Date(source['@timestamp']),
                service: source.service?.name || 'unknown',
                method: source.request?.method || 'unknown',
                path: source.request?.uri || 'unknown',
                status: source.response?.status || 0,
                requestBody: source.request_body || '',
                responseBody: source.response_body || '',
                latency: source.latency || 0,
                requestHeaders: source.request_headers || {},
                responseHeaders: source.response_headers || {}
            };
        });
        
        // Update services dropdown
        currentRequests.forEach(req => services.add(req.service));
        updateServiceFilter();
        
        // Apply filters and render
        applyFilters();
    }
    
    function updateServiceFilter() {
        const serviceFilter = document.getElementById('serviceFilter');
        const currentValue = serviceFilter.value;
        
        // Save existing options
        const options = Array.from(services).map(service => {
            return `<option value="${service}" ${service === currentValue ? 'selected' : ''}>${service}</option>`;
        });
        
        // Update dropdown with All option preserved
        serviceFilter.innerHTML = `<option value="">All Services</option>${options.join('')}`;
    }
    
    function applyFilters() {
        const serviceFilter = document.getElementById('serviceFilter').value;
        const statusFilter = document.getElementById('statusFilter').value;
        const methodFilter = document.getElementById('methodFilter').value;
        const searchFilter = document.getElementById('searchFilter').value.toLowerCase();
        
        const filteredRequests = currentRequests.filter(req => {
            // Service filter
            if (serviceFilter && req.service !== serviceFilter) return false;
            
            // Status filter
            if (statusFilter) {
                const statusClass = Math.floor(req.status / 100) + 'xx';
                if (statusClass !== statusFilter) return false;
            }
            
            // Method filter
            if (methodFilter && req.method !== methodFilter) return false;
            
            // Search filter (search in path, request body, or response body)
            if (searchFilter) {
                const requestBodyStr = typeof req.requestBody === 'string' ? req.requestBody : JSON.stringify(req.requestBody);
                const responseBodyStr = typeof req.responseBody === 'string' ? req.responseBody : JSON.stringify(req.responseBody);
                
                const searchableText = [
                    req.path,
                    requestBodyStr,
                    responseBodyStr
                ].join(' ').toLowerCase();
                
                if (!searchableText.includes(searchFilter)) return false;
            }
            
            return true;
        });
        
        renderRequests(filteredRequests);
    }
    
    function renderRequests(requests) {
        if (requests.length === 0) {
            document.getElementById('requests-container').innerHTML = `
                <div class="alert alert-info">
                    No requests found matching your filters.
                </div>
            `;
            return;
        }
        
        const html = requests.map(req => {
            const statusClass = req.status >= 200 && req.status < 300 ? 'success' : 
                               req.status >= 400 && req.status < 500 ? 'warning' : 
                               req.status >= 500 ? 'danger' : 'info';
            
            const requestBodyJson = formatJson(req.requestBody);
            const responseBodyJson = formatJson(req.responseBody);
            
            return `
                <div class="card request-card">
                    <div class="card-header bg-light d-flex justify-content-between">
                        <div>
                            <span class="badge bg-primary">${req.method}</span>
                            <span class="badge bg-${statusClass}">${req.status}</span>
                            <strong>${req.path}</strong>
                        </div>
                        <div>
                            <span class="badge bg-secondary">${req.service}</span>
                            <span class="text-muted">${formatTimestamp(req.timestamp)}</span>
                            <span class="badge bg-info">${req.latency.toFixed(2)}ms</span>
                        </div>
                    </div>
                    <div class="card-body">
                        <ul class="nav nav-tabs" id="req${req.id}" role="tablist">
                            <li class="nav-item" role="presentation">
                                <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#reqBody${req.id}">Request Body</button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#respBody${req.id}">Response Body</button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#reqHeaders${req.id}">Request Headers</button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#respHeaders${req.id}">Response Headers</button>
                            </li>
                        </ul>
                        <div class="tab-content p-3">
                            <div class="tab-pane fade show active" id="reqBody${req.id}">
                                <pre class="json-display"><code class="language-json">${requestBodyJson}</code></pre>
                            </div>
                            <div class="tab-pane fade" id="respBody${req.id}">
                                <pre class="json-display"><code class="language-json">${responseBodyJson}</code></pre>
                            </div>
                            <div class="tab-pane fade" id="reqHeaders${req.id}">
                                <pre class="json-display"><code class="language-json">${formatJson(req.requestHeaders)}</code></pre>
                            </div>
                            <div class="tab-pane fade" id="respHeaders${req.id}">
                                <pre class="json-display"><code class="language-json">${formatJson(req.responseHeaders)}</code></pre>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        document.getElementById('requests-container').innerHTML = html;
        
        // Initialize syntax highlighting
        document.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }
    
    function formatJson(data) {
        try {
            if (typeof data === 'string') {
                // Try to parse as JSON if it's a string
                const parsed = JSON.parse(data);
                return JSON.stringify(parsed, null, 2);
            } else {
                return JSON.stringify(data, null, 2);
            }
        } catch (e) {
            // If parsing fails, return as is (might be plain text)
            return data || '';
        }
    }
    
    function formatTimestamp(date) {
        return date.toLocaleTimeString() + ' ' + date.toLocaleDateString();
    }
});
