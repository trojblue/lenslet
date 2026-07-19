"""Network controller for delayed and overridden Metrics facet responses."""

from __future__ import annotations

from typing import Any


def install_facet_controller(page: Any) -> None:
    page.evaluate(
        """() => {
          if (window.__lensletFacetController) return;
          const originalFetch = window.fetch.bind(window);
          const controller = {
            delays: {},
            emptyFields: [],
            explicitEmptyFields: [],
            errorFields: [],
            categoryFields: [],
            metricRanges: {},
            requests: [],
            completions: [],
            folderRequests: [],
          };
          const jsonResponse = (response, body) => {
            const headers = new Headers(response.headers);
            headers.delete('content-length');
            headers.delete('content-encoding');
            headers.set('content-type', 'application/json');
            return new Response(JSON.stringify(body), {
              status: response.status,
              statusText: response.statusText,
              headers,
            });
          };
          window.__lensletFacetController = controller;
          window.fetch = async (...args) => {
            const input = args[0];
            const init = args[1] || {};
            const rawUrl = input instanceof Request ? input.url : String(input);
            const pathname = new URL(rawUrl, location.href).pathname;
            if (pathname === '/folders') {
              controller.folderRequests.push({ at: performance.now(), url: rawUrl });
            }
            if (pathname !== '/folders/facets') return originalFetch(...args);
            let payload = {};
            try {
              const rawBody = input instanceof Request ? await input.clone().text() : init.body;
              payload = rawBody ? JSON.parse(String(rawBody)) : {};
            } catch {}
            const facetFields = payload.facet_fields || {};
            const metricFields = facetFields.metric_keys || [];
            const categoricalFields = facetFields.categorical_keys || [];
            const fields = [...metricFields, ...categoricalFields];
            const delayMs = fields.reduce(
              (maximum, field) => Math.max(maximum, Number(controller.delays[field] || 0)),
              0,
            );
            controller.requests.push({
              at: performance.now(),
              metricFields,
              categoricalFields,
              delayMs,
            });
            const responseInit = { ...init };
            if (fields.includes('late_group')) delete responseInit.signal;
            const response = await originalFetch(input, responseInit);
            if (delayMs > 0) await new Promise(resolve => setTimeout(resolve, delayMs));
            controller.completions.push({
              at: performance.now(),
              metricFields,
              categoricalFields,
            });
            if (fields.some(field => controller.errorFields.includes(field))) {
              return new Response(JSON.stringify({ detail: 'forced facet probe failure' }), {
                status: 503,
                headers: { 'Content-Type': 'application/json' },
              });
            }
            const emptyFields = fields.filter(field => controller.emptyFields.includes(field));
            const explicitEmptyFields = fields.filter(
              field => controller.explicitEmptyFields.includes(field),
            );
            const categoryFields = metricFields.filter(field => controller.categoryFields.includes(field));
            const rangeFields = metricFields.filter(field => controller.metricRanges[field]);
            if (!emptyFields.length && !explicitEmptyFields.length && !categoryFields.length && !rangeFields.length) return response;
            const body = await response.json();
            for (const field of emptyFields) {
              if (metricFields.includes(field)) {
                body.metrics = body.metrics || {};
                delete body.metrics[field];
              }
              if (categoricalFields.includes(field)) {
                body.categoricals = body.categoricals || {};
                delete body.categoricals[field];
              }
            }
            for (const field of explicitEmptyFields) {
              if (metricFields.includes(field)) {
                body.metrics = body.metrics || {};
                body.metrics[field] = { histogram: null, categories: [] };
              }
              if (categoricalFields.includes(field)) {
                body.categoricals = body.categoricals || {};
                body.categoricals[field] = { values: [] };
              }
            }
            for (const field of categoryFields) {
              body.metrics = body.metrics || {};
              body.metrics[field] = body.metrics[field] || { histogram: null, categories: [] };
              body.metrics[field].categories = [
                { code: 0, label: 'low', population_count: 793 },
                { code: 1, label: 'high', population_count: 792 },
              ];
            }
            for (const field of rangeFields) {
              const histogram = body.metrics?.[field]?.histogram;
              const range = controller.metricRanges[field];
              if (!histogram || !Array.isArray(range)) continue;
              histogram.min = Number(range[0]);
              histogram.max = Number(range[1]);
            }
            return jsonResponse(response, body);
          };
        }"""
    )


def configure_facets(page: Any, **updates: Any) -> None:
    page.evaluate(
        """updates => {
          const controller = window.__lensletFacetController;
          if (!controller) throw new Error('facet controller is not installed');
          Object.assign(controller, updates);
        }""",
        updates,
    )
