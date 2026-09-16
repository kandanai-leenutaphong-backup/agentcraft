# Internal Dropdown Missing Because New Revision Was Not Ready

## Symptom

The internal URL served the old `kiosk-20260424-080233` bundle without the scenario dropdown even after deploying `kiosk-20260429-101347`. The public FQDN returned `/assets/index-B53ZvS2v.js`, which contained `ngm-busbar-trip` but not `scenario-picker` or `atc-tcas-cascade`.

## Root cause

`Dockerfile.kiosk` was switched from Docker Hub nginx to `mcr.microsoft.com/cbl-mariner/base/nginx:1.22` to avoid Docker Hub rate limits. The new runtime image accepted `/etc/nginx/conf.d/default.conf`, but its main nginx configuration was not made explicit for this project. The new Container Apps revision `gridiq-internal--0000006` stayed `Activating`, so Container Apps continued serving the last ready revision `gridiq-internal--0000004`.

## Problematic code

```dockerfile
RUN mkdir -p /etc/nginx/conf.d && rm -f /etc/nginx/conf.d/default.conf
COPY deploy/nginx.kiosk.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
```

## Fix

```dockerfile
RUN mkdir -p /etc/nginx/conf.d && rm -f /etc/nginx/conf.d/default.conf
COPY deploy/nginx.kiosk.main.conf /etc/nginx/nginx.conf
COPY deploy/nginx.kiosk.conf /etc/nginx/conf.d/default.conf

RUN nginx -t && grep -R "listen 8080" /etc/nginx/conf.d/default.conf >/dev/null

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
```

## Files changed

- `Dockerfile.kiosk`: adds build-time checks for the scenario picker, ATC scenario identifier, nginx syntax, and port-8080 server block.
- `deploy/nginx.kiosk.main.conf`: adds explicit nginx main config for the MCR CBL-Mariner nginx runtime image.
- `AUTODEV.md`: documents the split nginx main/server config and updated Dockerfile behavior.

## Regression test

- `Dockerfile.kiosk`: build-time smoke checks fail the image if `dist/assets` lacks `scenario-picker` or `atc-tcas-cascade`, or if nginx does not parse a server block listening on `8080`.
- Live verification: `curl /healthz` returned `ok`, the served JS bundle contained `scenario-picker`, `atc-tcas-cascade`, and `TCAS RA Go-Around Cascade`, and the browser showed the dropdown with Energy and Air Traffic Control groups.