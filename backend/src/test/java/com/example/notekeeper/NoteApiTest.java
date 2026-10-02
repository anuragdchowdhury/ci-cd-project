package com.example.notekeeper;

import static org.junit.jupiter.api.Assertions.*;
import java.net.*;
import java.net.http.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class NoteApiTest {
    @Value("${local.server.port}") int port;
    HttpClient client = HttpClient.newHttpClient();
    HttpResponse<String> request(String method, String path, String body) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
            .header("Content-Type", "application/json");
        return client.send(builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }
    @Test void crudAndValidation() throws Exception {
        var created = request("POST", "/api/notes", "{\"title\":\"First note\",\"content\":\"Hello\"}");
        assertEquals(201, created.statusCode());
        assertTrue(created.headers().firstValue("X-Request-Id").isPresent());
        String path = created.headers().firstValue("Location").orElseThrow();
        assertEquals(200, request("GET", path, null).statusCode());
        assertTrue(request("GET", "/api/notes", null).body().contains("First note"));
        assertEquals(200, request("PUT", path, "{\"title\":\"Updated\",\"content\":\"Body\"}").statusCode());
        assertEquals(204, request("DELETE", path, null).statusCode());
        assertEquals(404, request("GET", path, null).statusCode());
        assertEquals(400, request("POST", "/api/notes", "{\"title\":\" \",\"content\":\"\"}").statusCode());
        assertEquals(400, request("GET", "/api/notes?size=1000", null).statusCode());
        assertEquals(400, request("GET", "/api/notes/not-a-uuid", null).statusCode());
    }
}
