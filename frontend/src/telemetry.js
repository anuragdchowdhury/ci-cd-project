import { ApplicationInsights, DistributedTracingModes } from '@microsoft/applicationinsights-web';

export function initializeTelemetry(config) {
  if (!config.applicationInsightsConnectionString) return null;
  const appInsights = new ApplicationInsights({ config: {
    connectionString: config.applicationInsightsConnectionString,
    distributedTracingMode: DistributedTracingModes.W3C,
    enableAutoRouteTracking: false,
    enableCorsCorrelation: false,
    disableCookiesUsage: true,
    samplingPercentage: 100,
    enableAjaxErrorStatusText: false,
    enableAjaxPerfTracking: false,
  } });
  appInsights.loadAppInsights();
  appInsights.addTelemetryInitializer((item) => {
    // Never attach note titles/bodies, identity data, tokens or URL query strings.
    const data = item.baseData;
    for (const field of ['uri', 'url', 'data']) {
      if (data && typeof data[field] === 'string') {
        try { const url = new URL(data[field], location.origin); data[field] = `${url.origin}${url.pathname}`; }
        catch { /* Non-URL data is left for the SDK. */ }
      }
    }
    item.data = { environment: config.environment, service: 'notekeeper-web' };
    return true;
  });
  appInsights.trackPageView({ name: 'NoteKeeper', uri: `${location.origin}${location.pathname}` });
  return appInsights;
}
