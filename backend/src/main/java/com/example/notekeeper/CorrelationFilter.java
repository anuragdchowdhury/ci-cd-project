package com.example.notekeeper;

import io.opentelemetry.api.trace.Span;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String requestId = UUID.randomUUID().toString();
        var spanContext = Span.current().getSpanContext();
        MDC.put("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);
        if (spanContext.isValid()) {
            MDC.put("traceId", spanContext.getTraceId());
            MDC.put("spanId", spanContext.getSpanId());
            response.setHeader("X-Trace-Id", spanContext.getTraceId());
        }
        try { chain.doFilter(request, response); }
        finally { MDC.remove("requestId"); MDC.remove("traceId"); MDC.remove("spanId"); }
    }
}
