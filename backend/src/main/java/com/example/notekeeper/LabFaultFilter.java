package com.example.notekeeper;

import io.opentelemetry.api.trace.Span;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Bounded operator-controlled drills. No public query parameter enables faults. */
@Component
@Order(1)
public class LabFaultFilter extends OncePerRequestFilter {
    private static final Logger LOG = LoggerFactory.getLogger(LabFaultFilter.class);
    private final String mode;
    public LabFaultFilter(@Value("${LAB_FAULT_MODE:none}") String mode) {
        if (!java.util.Set.of("none", "error", "latency", "cpu").contains(mode)) {
            throw new IllegalArgumentException("Unsupported lab fault mode");
        }
        this.mode = mode;
    }
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                   FilterChain chain) throws ServletException, IOException {
        if (!request.getRequestURI().startsWith("/api/notes") || mode.equals("none")) {
            chain.doFilter(request, response);
            return;
        }
        Span.current().setAttribute("lab.scenario", mode);
        if (mode.equals("error")) {
            LOG.error("Controlled lab failure scenario=error");
            response.setStatus(500);
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"Controlled lab failure\"}");
            return;
        }
        if (mode.equals("latency")) {
            try { Thread.sleep(1500); }
            catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new ServletException("Interrupted lab delay", exception);
            }
        }
        if (mode.equals("cpu")) {
            long until = System.nanoTime() + 50_000_000L;
            while (System.nanoTime() < until) { Thread.onSpinWait(); }
        }
        chain.doFilter(request, response);
    }
}
