const raml2obj = require('raml2obj');

const file = process.argv[2];

if (!file) {
    console.error("Usage: node convert_raml.js <path-to-raml>");
    process.exit(1);
}

raml2obj.parse(file).then(ramlObj => {
    const openapi = {
        openapi: '3.0.0',
        info: { title: ramlObj.title || 'Converted API', version: ramlObj.version || '1.0' },
        paths: {}
    };

    if (ramlObj.resources) {
        ramlObj.resources.forEach(res => {
            const path = res.relativeUri;
            openapi.paths[path] = {};
            if (res.methods) {
                res.methods.forEach(m => {
                    openapi.paths[path][m.method] = {
                        responses: { '200': { description: 'Success' } }
                    };
                    if (m.queryParameters) {
                        openapi.paths[path][m.method].parameters = m.queryParameters.map(qp => ({
                            name: qp.name,
                            in: 'query',
                            required: qp.required || false,
                            schema: { type: qp.type || 'string' }
                        }));
                    }
                });
            }
        });
    }

    console.log(JSON.stringify(openapi, null, 2));

}).catch(err => {
    console.error("Error parsing RAML:", err);
    process.exit(1);
});
