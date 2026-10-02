package com.example.notekeeper;

import java.time.Instant;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import org.slf4j.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ApiErrors {
    private static final Logger log = LoggerFactory.getLogger(ApiErrors.class);
    public record ApiError(Instant timestamp, int status, String message, String requestId, String traceId) { }
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<ApiError> status(ResponseStatusException ex) {
        return error(ex.getStatusCode().value(), ex.getReason());
    }
    @ExceptionHandler({MethodArgumentNotValidException.class, HttpMessageNotReadableException.class,
                      MethodArgumentTypeMismatchException.class})
    ResponseEntity<ApiError> validation(Exception ex) { return error(400, "Invalid request"); }
    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiError> unexpected(Exception ex) {
        // Avoid logging user note text, SQL parameters or secrets.
        log.error("Request failed: {}", ex.getClass().getSimpleName());
        Span.current().recordException(new RuntimeException("Request failed: " + ex.getClass().getSimpleName()));
        Span.current().setStatus(StatusCode.ERROR);
        return error(500, "Request failed");
    }
    private ResponseEntity<ApiError> error(int status, String message) {
        return ResponseEntity.status(status).body(new ApiError(Instant.now(), status, message,
            MDC.get("requestId"), MDC.get("traceId")));
    }
}
