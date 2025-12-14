package com.soma.maa.service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.eclipse.microprofile.config.inject.ConfigProperty;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.soma.maa.model.ParserResult;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.core.Response;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@ApplicationScoped
public class Bc3ParserService {
  
  @ConfigProperty(name = "bc3.parser.python.path", defaultValue = "python3")
  String pythonPath;
  
  @ConfigProperty(name = "bc3.parser.script.path", defaultValue = "src/main/python/parser_wrapper.py")
  String scriptPath;
  
  @ConfigProperty(name = "bc3.parser.timeout.seconds", defaultValue = "300")
  int timeoutSeconds;
  
  @Inject
  ObjectMapper objectMapper;
  
  public Response process(InputStream bc3FileStream) {
    String threadName = Thread.currentThread().getName();
    
    try {
      // Read the BC3 file into a byte array
      byte[] bc3Data = bc3FileStream.readAllBytes();
      long byteCount = bc3Data.length;
      log.info("Received BC3 file with {} bytes on thread: {}", byteCount, threadName);
      
      // Call Python parser
      String jsonResult = callPythonParser(bc3Data);
      
      // Parse the result
      JsonNode resultNode = objectMapper.readTree(jsonResult);
      boolean success = resultNode.get("success").asBoolean();
      
      if (!success) {
        String error = resultNode.get("error").asText();
        log.error("Python parser failed: {}", error);
        return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
            .entity(new ParserResult("Parser error: " + error, byteCount, threadName))
            .build();
      }
      
      // Get the parsed data
      JsonNode data = resultNode.get("data");
      log.info("Successfully parsed BC3 file with {} bytes", byteCount);
      
      // Return the parsed JSON tree directly
      return Response.ok()
          .entity(data)
          .build();
      
    } catch (IOException e) {
      log.error("Error reading BC3 file: {}", e.getMessage(), e);
      return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
          .entity(new ParserResult("Error reading BC3 file: " + e.getMessage(), 0, threadName))
          .build();
    } catch (Exception e) {
      log.error("Error processing BC3 file: {}", e.getMessage(), e);
      return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
          .entity(new ParserResult("Error processing BC3 file: " + e.getMessage(), 0, threadName))
          .build();
    }
  }
  
  private String callPythonParser(byte[] bc3Data) throws IOException, InterruptedException {
    log.info("Calling Python parser: {} {}", pythonPath, scriptPath);
    
    // Build the process
    ProcessBuilder processBuilder = new ProcessBuilder(pythonPath, scriptPath);
    processBuilder.redirectErrorStream(false);
    
    Process process = processBuilder.start();
    
    try {
      // Write BC3 data to process stdin
      process.getOutputStream().write(bc3Data);
      process.getOutputStream().flush();
      process.getOutputStream().close();
      
      // Read stdout (JSON result)
      StringBuilder output = new StringBuilder();
      try (BufferedReader reader = new BufferedReader(
          new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
        String line;
        while ((line = reader.readLine()) != null) {
          output.append(line).append("\n");
        }
      }
      
      // Read stderr (for logging)
      StringBuilder errors = new StringBuilder();
      try (BufferedReader reader = new BufferedReader(
          new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8))) {
        String line;
        while ((line = reader.readLine()) != null) {
          errors.append(line).append("\n");
        }
      }
      
      // Wait for process to complete with timeout
      boolean completed = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
      
      if (!completed) {
        process.destroyForcibly();
        throw new IOException("Python parser timed out after " + timeoutSeconds + " seconds");
      }
      
      int exitCode = process.exitValue();
      
      if (errors.length() > 0) {
        log.warn("Python parser stderr: {}", errors.toString());
      }
      
      if (exitCode != 0 && exitCode != 1) {
        // Exit code 1 is used for controlled errors in the Python script
        throw new IOException("Python parser exited with code " + exitCode + ": " + errors.toString());
      }
      
      return output.toString().trim();
      
    } finally {
      process.destroy();
    }
  }
}
