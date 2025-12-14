package com.soma.maa.api;

import java.io.InputStream;

import org.jboss.resteasy.reactive.PartType;
import org.jboss.resteasy.reactive.RestForm;

import com.soma.maa.service.Bc3ParserService;
import com.soma.maa.model.ParserResult;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import lombok.extern.slf4j.Slf4j;

@Path("/parse/bc3")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.MULTIPART_FORM_DATA)
@Slf4j
@ApplicationScoped
public class Bc3ParserApi {

  private Bc3ParserService bc3ParserService;

  @Inject
  public Bc3ParserApi(Bc3ParserService bc3ParserService) {
    this.bc3ParserService = bc3ParserService;
  }

  @GET
  public Response healthCheck() {
    return Response.ok("BC3 Parser API is running").build();
  }

  @POST
  public Response uploadAndParseBc3(@RestForm("file") InputStream bc3FileStream) {

    String threadName = Thread.currentThread().getName();
    log.info("Executing on thread: {}", threadName);
    log.info("Received file stream: {}", bc3FileStream != null ? "not null" : "null");

    if (bc3FileStream == null) {
      log.warn("No file stream received");
      return Response.status(Response.Status.BAD_REQUEST)
          .entity(new ParserResult("No file uploaded", 0, threadName))
          .build();
    }

    try {
      log.info("Starting to process BC3 file");
      Response response = bc3ParserService.process(bc3FileStream);
      log.info("Finished processing BC3 file");
      return response;
    }
    catch (Exception e) {
      log.error("Unexpected error: {}", e.getMessage(), e);
      return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
        .entity(new ParserResult("An unexpected error occurred: " + e.getMessage(), 0, threadName))
        .build();
    }
  }
}
