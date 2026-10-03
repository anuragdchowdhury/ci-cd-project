package com.example.notekeeper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoteKeeperApplication {
    public static void main(String[] args) {
        var context = SpringApplication.run(NoteKeeperApplication.class, args);
        if (Boolean.parseBoolean(System.getenv("APP_MIGRATE_ONLY"))) {
            // Flyway has completed during startup. Closing the non-web context
            // makes the same release image usable as a finite Kubernetes Job.
            context.close();
        }
    }
}
