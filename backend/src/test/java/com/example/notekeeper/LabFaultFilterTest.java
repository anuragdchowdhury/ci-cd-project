package com.example.notekeeper;

import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class LabFaultFilterTest {
    @Test void injectedErrorDoesNotExecuteDatabaseRequest() throws Exception {
        var request = new MockHttpServletRequest("GET", "/api/notes");
        var response = new MockHttpServletResponse();
        var executed = new AtomicBoolean();
        new LabFaultFilter("error").doFilter(request, response, (req,res) -> executed.set(true));
        assertEquals(500, response.getStatus());
        assertFalse(executed.get());
        assertEquals("application/json", response.getContentType());
    }
    @Test void healthProbesRemainHealthyDuringErrorDrill() throws Exception {
        var executed = new AtomicBoolean();
        new LabFaultFilter("error").doFilter(new MockHttpServletRequest("GET", "/actuator/health/liveness"),
            new MockHttpServletResponse(), (req,res) -> executed.set(true));
        assertTrue(executed.get());
    }
    @Test void unknownFaultCannotSilentlyActivate() {
        assertThrows(IllegalArgumentException.class, () -> new LabFaultFilter("arbitrary"));
    }
}
