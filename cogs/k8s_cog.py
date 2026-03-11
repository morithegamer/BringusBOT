import discord
from discord.ext import commands
from discord import app_commands
from kubernetes import client, config
from kubernetes.client import V1Pod, V1Deployment, V1Namespace, V1Node, V1Service
from kubernetes.client.exceptions import ApiException
import shlex
from typing import Optional, Tuple, List
import io

# Load kube config for local testing. Use load_incluster_config() for in-cluster.
try:
    config.load_incluster_config()
except Exception:
    config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()
networking_v1 = client.NetworkingV1Api()
custom_objects = client.CustomObjectsApi()

MAX_FIELD_LEN = 900  # keep fields short to avoid embed limits
MAX_MESSAGE_LEN = 1900

class KubernetesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _parse_namespace(self, args: List[str]) -> Tuple[Optional[str], bool]:
        ns: Optional[str] = None
        all_ns = False
        if "-A" in args or "--all-namespaces" in args:
            all_ns = True
        if "-n" in args:
            try:
                ns_val = args[args.index("-n") + 1]
                ns = ns_val
            except Exception:
                pass
        return ns, all_ns

    def _parse_selector(self, args: List[str]) -> Optional[str]:
        if "-l" in args:
            try:
                return args[args.index("-l") + 1]
            except Exception:
                return None
        return None

    def _truncate(self, text: str, limit: int = MAX_MESSAGE_LEN) -> str:
        return text if len(text) <= limit else text[: limit - 20] + "\n...[truncated]"

    @app_commands.command(name="kubectl", description="Run a basic kubectl-like command.")
    @app_commands.describe(command="Examples: 'get pods -n default', 'describe pod mypod -n ns', 'logs mypod -n ns -c container --tail 200'")
    async def kubectl(self, interaction: discord.Interaction, command: str):
        try:
            args = shlex.split(command)
            if not args:
                await interaction.response.send_message("❌ Provide a command, e.g. 'get pods'", ephemeral=True)
                return

            verb = args[0]
            ns, all_ns = self._parse_namespace(args)

            if verb == "get":
                if len(args) < 2:
                    await interaction.response.send_message("❌ Usage: get <resource> [-n ns|-A]", ephemeral=True)
                    return
                resource = args[1]
                selector = self._parse_selector(args)
                await self._kubectl_get(interaction, resource, ns, all_ns, selector)
                return

            if verb == "describe":
                if len(args) < 3:
                    await interaction.response.send_message("❌ Usage: describe <resource> <name> [-n ns]", ephemeral=True)
                    return
                resource, name = args[1], args[2]
                await self._kubectl_describe(interaction, resource, name, ns)
                return

            if verb == "logs":
                if len(args) < 2:
                    await interaction.response.send_message("❌ Usage: logs <pod> [-n ns] [-c container] [--tail N]", ephemeral=True)
                    return
                pod_name = args[1]
                # flags
                container: Optional[str] = None
                tail_lines: int = 200
                since_seconds: Optional[int] = None
                previous: bool = False
                if "-c" in args:
                    try:
                        container = args[args.index("-c") + 1]
                    except Exception:
                        pass
                if "--tail" in args:
                    try:
                        tail_lines = int(args[args.index("--tail") + 1])
                    except Exception:
                        pass
                if "--since" in args:
                    try:
                        val = args[args.index("--since") + 1]
                        if val.endswith("m"):
                            since_seconds = int(val[:-1]) * 60
                        elif val.endswith("h"):
                            since_seconds = int(val[:-1]) * 3600
                        else:
                            since_seconds = int(val)
                    except Exception:
                        pass
                if "--previous" in args:
                    previous = True
                await self._kubectl_logs(interaction, pod_name, ns or "default", container, tail_lines, since_seconds, previous)
                return

            if verb == "scale":
                # scale deployment <name> --replicas N [-n ns]
                if len(args) < 4 or args[1] not in ["deployment", "deploy", "deployments"]:
                    await interaction.response.send_message("❌ Usage: scale deployment <name> --replicas N [-n ns]", ephemeral=True)
                    return
                name = args[2]
                replicas = None
                if "--replicas" in args:
                    try:
                        replicas = int(args[args.index("--replicas") + 1])
                    except Exception:
                        pass
                if replicas is None:
                    await interaction.response.send_message("❌ Missing --replicas N", ephemeral=True)
                    return
                await self._kubectl_scale_deployment(interaction, name, ns or "default", replicas)
                return

            if verb == "rollout":
                # rollout restart deployment <name> [-n ns]
                if len(args) < 3:
                    await interaction.response.send_message("❌ Usage: rollout restart <deployment|dc> <name> [-n ns]", ephemeral=True)
                    return
                action = args[1]
                if action == "restart":
                    if len(args) < 4:
                        await interaction.response.send_message("❌ Usage: rollout restart <deployment|dc> <name> [-n ns]", ephemeral=True)
                        return
                    kind = args[2]
                    name = args[3]
                    if kind in ["deployment", "deploy", "deployments"]:
                        await self._kubectl_rollout_restart(interaction, name, ns or "default")
                        return
                    if kind in ["dc", "deploymentconfig", "deploymentconfigs"]:
                        await self._oc_rollout_restart_dc(interaction, name, ns or "default")
                        return
                await interaction.response.send_message("❌ Usage: rollout restart <deployment|dc> <name> [-n ns]", ephemeral=True)
                return

            if verb == "top":
                # top pods [-n ns] | top nodes
                if len(args) < 2:
                    await interaction.response.send_message("❌ Usage: top <pods|nodes> [-n ns]", ephemeral=True)
                    return
                what = args[1]
                await self._kubectl_top(interaction, what, ns or "default")
                return

            if verb == "whoami":
                # OpenShift whoami (if permissions allow)
                await self._oc_whoami(interaction)
                return

            await interaction.response.send_message("❌ Supported: get, describe, logs, scale, rollout, top, whoami.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"⚠️ Error: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Error: {str(e)}", ephemeral=True)

    async def _kubectl_get(self, interaction: discord.Interaction, resource: str, ns: Optional[str], all_ns: bool, selector: Optional[str]):
        resource = resource.lower()
        embed: discord.Embed

        try:
            # Namespaces
            if resource in ["namespaces", "ns"]:
                ns_list = v1.list_namespace().items
                embed = discord.Embed(title="☸️ Kubernetes Namespaces", color=discord.Color.blurple())
                for item in ns_list[:25]:
                    name = item.metadata.name if getattr(item, "metadata", None) and getattr(item.metadata, "name", None) else "?"
                    status = getattr(getattr(item, "status", None), 'phase', None) or "Active"
                    embed.add_field(name=name, value=status, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Nodes
            if resource in ["nodes", "no"]:
                nodes = v1.list_node().items
                embed = discord.Embed(title="☸️ Kubernetes Nodes", color=discord.Color.blurple())
                for node in nodes[:25]:
                    ready_cond = None
                    if getattr(getattr(node, "status", None), "conditions", None):
                        ready_cond = next((c for c in node.status.conditions if c.type == "Ready"), None)
                    status = "Ready" if ready_cond and getattr(ready_cond, "status", None) == "True" else "NotReady"
                    version = getattr(getattr(getattr(node, "status", None), "node_info", None), "kubelet_version", None) or "?"
                    node_name = getattr(getattr(node, "metadata", None), "name", None) or "?"
                    embed.add_field(name=node_name, value=f"{status} • {version}", inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # From here, namespaced resources
            namespace = None if all_ns else (ns or "default")

            # Pods
            if resource in ["pods", "po"]:
                if all_ns:
                    pods = v1.list_pod_for_all_namespaces(label_selector=selector or None).items
                else:
                    pods = v1.list_namespaced_pod(namespace, label_selector=selector or None).items
                if not pods:
                    await interaction.response.send_message(
                        f"No pods found in `{namespace or 'all-namespaces'}`.", ephemeral=True
                    )
                    return
                title_ns = namespace or "all namespaces"
                embed = discord.Embed(title=f"☸️ Pods in `{title_ns}`", color=discord.Color.green())
                for pod in pods[:10]:
                    ns_name = getattr(getattr(pod, "metadata", None), "namespace", None) or "?"
                    phase = getattr(getattr(pod, "status", None), "phase", None) or "?"
                    pod_name = getattr(getattr(pod, "metadata", None), "name", None) or "?"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=pod_name + extra, value=phase, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Deployments
            if resource in ["deployments", "deploy", "deployment", "deploys"]:
                if all_ns:
                    deployments = apps_v1.list_deployment_for_all_namespaces(label_selector=selector or None).items
                else:
                    deployments = apps_v1.list_namespaced_deployment(namespace, label_selector=selector or None).items
                title_ns = namespace or "all namespaces"
                embed = discord.Embed(title=f"☸️ Deployments in `{title_ns}`", color=discord.Color.teal())
                if not deployments:
                    embed.description = "No deployments found."
                for dep in deployments[:15]:
                    ns_name = getattr(getattr(dep, "metadata", None), "namespace", None) or "?"
                    replicas = getattr(getattr(dep, "status", None), "replicas", None) or 0
                    ready = getattr(getattr(dep, "status", None), "ready_replicas", None) or 0
                    dep_name = getattr(getattr(dep, "metadata", None), "name", None) or "?"
                    val = f"{ready}/{replicas} ready"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=dep_name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Services
            if resource in ["services", "svc", "service"]:
                if all_ns:
                    services = v1.list_service_for_all_namespaces(label_selector=selector or None).items
                else:
                    services = v1.list_namespaced_service(namespace, label_selector=selector or None).items
                title_ns = namespace or "all namespaces"
                embed = discord.Embed(title=f"☸️ Services in `{title_ns}`", color=discord.Color.orange())
                if not services:
                    embed.description = "No services found."
                for svc in services[:15]:
                    ns_name = getattr(getattr(svc, "metadata", None), "namespace", None) or "?"
                    stype = getattr(getattr(svc, "spec", None), "type", None) or "?"

                    cluster_ip = getattr(getattr(svc, "spec", None), "cluster_ip", None) or "?"
                    port_objs = getattr(getattr(svc, "spec", None), "ports", None) or []
                    ports_str = ",".join([f"{p.port}/{p.protocol}" for p in port_objs if getattr(p, 'port', None) is not None])
                    val = f"{stype} • {cluster_ip} • {ports_str}"
                    svc_name = getattr(getattr(svc, "metadata", None), "name", None) or "?"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=svc_name + extra, value=val[:MAX_FIELD_LEN], inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Events (namespaced only for simplicity)
            if resource in ["events", "ev"]:
                title_ns = namespace or "all namespaces"
                if all_ns:
                    try:
                        events_list = v1.list_event_for_all_namespaces().items
                    except Exception:
                        await interaction.response.send_message("❌ All-namespace events not supported by this client.", ephemeral=True)
                        return
                else:
                    events_list = v1.list_namespaced_event(namespace).items
                embed = discord.Embed(title=f"☸️ Events in `{title_ns}`", color=discord.Color.dark_gold())
                for ev in events_list[:10]:
                    involved = getattr(ev, 'involved_object', None)
                    ref_kind = getattr(involved, 'kind', None) or 'object'
                    ref_name = getattr(involved, 'name', None) or ''
                    ref = f"{ref_kind}/{ref_name}".strip('/')
                    msg = (getattr(ev, 'message', '') or '').strip()
                    ts = getattr(ev, 'last_timestamp', None) or getattr(ev, 'event_time', None) or getattr(ev, 'first_timestamp', None)
                    stamp = ts.isoformat() if ts else ""
                    value = (f"{msg}\n{stamp}").strip()
                    embed.add_field(name=f"{ref}", value=value or "(no message)", inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # StatefulSets
            if resource in ["statefulsets", "sts", "statefulset"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    stss = apps_v1.list_stateful_set_for_all_namespaces(label_selector=selector or None).items
                else:
                    stss = apps_v1.list_namespaced_stateful_set(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ StatefulSets in `{title}`", color=discord.Color.teal())
                if not stss:
                    embed.description = "No statefulsets found."
                for ss in stss[:15]:
                    ns_name = getattr(getattr(ss, "metadata", None), "namespace", None) or "?"
                    replicas = getattr(getattr(ss, "status", None), "replicas", None) or 0
                    ready = getattr(getattr(ss, "status", None), "ready_replicas", None) or 0
                    name = getattr(getattr(ss, "metadata", None), "name", None) or "?"
                    val = f"{ready}/{replicas} ready"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Jobs
            if resource in ["jobs", "job"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    jobs = batch_v1.list_job_for_all_namespaces(label_selector=selector or None).items
                else:
                    jobs = batch_v1.list_namespaced_job(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ Jobs in `{title}`", color=discord.Color.blue())
                if not jobs:
                    embed.description = "No jobs found."
                for job in jobs[:15]:
                    ns_name = getattr(getattr(job, "metadata", None), "namespace", None) or "?"
                    succeeded = getattr(getattr(job, "status", None), "succeeded", None) or 0
                    active = getattr(getattr(job, "status", None), "active", None) or 0
                    failed = getattr(getattr(job, "status", None), "failed", None) or 0
                    name = getattr(getattr(job, "metadata", None), "name", None) or "?"
                    val = f"succeeded:{succeeded} active:{active} failed:{failed}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # CronJobs
            if resource in ["cronjobs", "cj", "cronjob"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    cjs = batch_v1.list_cron_job_for_all_namespaces(label_selector=selector or None).items
                else:
                    cjs = batch_v1.list_namespaced_cron_job(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ CronJobs in `{title}`", color=discord.Color.blue())
                if not cjs:
                    embed.description = "No cronjobs found."
                for cj in cjs[:15]:
                    ns_name = getattr(getattr(cj, "metadata", None), "namespace", None) or "?"
                    schedule = getattr(getattr(cj, "spec", None), "schedule", None) or "?"
                    suspend = getattr(getattr(cj, "spec", None), "suspend", None)
                    name = getattr(getattr(cj, "metadata", None), "name", None) or "?"
                    val = f"{schedule} • {'suspended' if suspend else 'active'}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # PVCs
            if resource in ["pvc", "pvcs", "persistentvolumeclaims"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    pvcs = v1.list_persistent_volume_claim_for_all_namespaces(label_selector=selector or None).items
                else:
                    pvcs = v1.list_namespaced_persistent_volume_claim(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ PVCs in `{title}`", color=discord.Color.dark_blue())
                if not pvcs:
                    embed.description = "No PVCs found."
                for pvc in pvcs[:15]:
                    ns_name = getattr(getattr(pvc, "metadata", None), "namespace", None) or "?"
                    status = getattr(getattr(pvc, "status", None), "phase", None) or "?"
                    capacity = ((getattr(getattr(pvc, "status", None), "capacity", None) or {}).get("storage")) or "?"
                    name = getattr(getattr(pvc, "metadata", None), "name", None) or "?"
                    val = f"{status} • {capacity}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # PVs (cluster-wide)
            if resource in ["pv", "pvs", "persistentvolumes"]:
                pvs = v1.list_persistent_volume().items
                embed = discord.Embed(title="☸️ PVs", color=discord.Color.dark_blue())
                if not pvs:
                    embed.description = "No PVs found."
                for pv in pvs[:15]:
                    status = getattr(getattr(pv, "status", None), "phase", None) or "?"
                    capacity = ((getattr(getattr(pv, "spec", None), "capacity", None) or {}).get("storage")) or "?"
                    name = getattr(getattr(pv, "metadata", None), "name", None) or "?"
                    claim_ref = getattr(getattr(pv, "spec", None), "claim_ref", None)
                    claim = f"{getattr(claim_ref, 'namespace', '?')}/{getattr(claim_ref, 'name', '?')}" if claim_ref else "-"
                    val = f"{status} • {capacity} • {claim}"
                    embed.add_field(name=name, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # ConfigMaps
            if resource in ["configmaps", "cm", "configmap"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    cms = v1.list_config_map_for_all_namespaces(label_selector=selector or None).items
                else:
                    cms = v1.list_namespaced_config_map(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ ConfigMaps in `{title}`", color=discord.Color.dark_gold())
                if not cms:
                    embed.description = "No configmaps found."
                for cm in cms[:15]:
                    ns_name = getattr(getattr(cm, "metadata", None), "namespace", None) or "?"
                    data_keys = list((getattr(cm, 'data', None) or {}).keys())
                    name = getattr(getattr(cm, "metadata", None), "name", None) or "?"
                    val = f"keys: {', '.join(data_keys)[:60]}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Secrets (mask values)
            if resource in ["secrets", "secret"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    secs = v1.list_secret_for_all_namespaces(label_selector=selector or None).items
                else:
                    secs = v1.list_namespaced_secret(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ Secrets in `{title}`", color=discord.Color.dark_gold())
                if not secs:
                    embed.description = "No secrets found."
                for sec in secs[:15]:
                    ns_name = getattr(getattr(sec, "metadata", None), "namespace", None) or "?"
                    type_ = getattr(getattr(sec, "type", None), "value", None) or getattr(sec, 'type', None) or "?"
                    name = getattr(getattr(sec, "metadata", None), "name", None) or "?"
                    keys = list((getattr(sec, 'data', None) or {}).keys())
                    val = f"{type_} • keys: {', '.join(keys)[:60]}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # Ingresses
            if resource in ["ingresses", "ing", "ingress"]:
                title_ns = (ns or "default") if not all_ns else None
                if all_ns:
                    ings = networking_v1.list_ingress_for_all_namespaces(label_selector=selector or None).items
                else:
                    ings = networking_v1.list_namespaced_ingress(title_ns, label_selector=selector or None).items
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ Ingresses in `{title}`", color=discord.Color.purple())
                if not ings:
                    embed.description = "No ingresses found."
                for ing in ings[:15]:
                    ns_name = getattr(getattr(ing, "metadata", None), "namespace", None) or "?"
                    rules = getattr(getattr(ing, "spec", None), "rules", None) or []
                    hosts = ",".join([getattr(r, 'host', '') or '' for r in rules])
                    name = getattr(getattr(ing, "metadata", None), "name", None) or "?"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=hosts or '-', inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # OpenShift: Routes
            if resource in ["routes", "route"]:
                title_ns = (ns or "default") if not all_ns else None
                try:
                    if all_ns:
                        routes = custom_objects.list_cluster_custom_object("route.openshift.io", "v1", "routes", label_selector=selector or None).get("items", [])
                    else:
                        routes = custom_objects.list_namespaced_custom_object("route.openshift.io", "v1", title_ns, "routes", label_selector=selector or None).get("items", [])
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ Routes not available: {ae}", ephemeral=True)
                    return
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ Routes in `{title}`", color=discord.Color.red())
                if not routes:
                    embed.description = "No routes found."
                for rt in routes[:15]:
                    meta = rt.get("metadata", {})
                    spec = rt.get("spec", {})
                    ns_name = meta.get("namespace", "?")
                    name = meta.get("name", "?")
                    host = spec.get("host", "-")
                    to = spec.get("to", {})
                    to_name = to.get("name", "?")
                    tls = spec.get("tls", {})
                    term = tls.get("termination", "")
                    val = f"{host} → {to_name} {'• TLS:'+term if term else ''}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val[:MAX_FIELD_LEN], inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # OpenShift: DeploymentConfigs
            if resource in ["deploymentconfigs", "dc", "deploymentconfig"]:
                title_ns = (ns or "default") if not all_ns else None
                try:
                    if all_ns:
                        dcs = custom_objects.list_cluster_custom_object("apps.openshift.io", "v1", "deploymentconfigs", label_selector=selector or None).get("items", [])
                    else:
                        dcs = custom_objects.list_namespaced_custom_object("apps.openshift.io", "v1", title_ns, "deploymentconfigs", label_selector=selector or None).get("items", [])
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ DeploymentConfigs not available: {ae}", ephemeral=True)
                    return
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ DeploymentConfigs in `{title}`", color=discord.Color.teal())
                if not dcs:
                    embed.description = "No deploymentconfigs found."
                for dc in dcs[:15]:
                    meta = dc.get("metadata", {})
                    status = dc.get("status", {})
                    ns_name = meta.get("namespace", "?")
                    name = meta.get("name", "?")
                    replicas = status.get("replicas") or dc.get("spec", {}).get("replicas", 0)
                    ready = status.get("availableReplicas", 0)
                    val = f"{ready}/{replicas} ready"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # OpenShift: ImageStreams
            if resource in ["imagestreams", "is", "imagestream"]:
                title_ns = (ns or "default") if not all_ns else None
                try:
                    if all_ns:
                        iss = custom_objects.list_cluster_custom_object("image.openshift.io", "v1", "imagestreams", label_selector=selector or None).get("items", [])
                    else:
                        iss = custom_objects.list_namespaced_custom_object("image.openshift.io", "v1", title_ns, "imagestreams", label_selector=selector or None).get("items", [])
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ ImageStreams not available: {ae}", ephemeral=True)
                    return
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ ImageStreams in `{title}`", color=discord.Color.orange())
                if not iss:
                    embed.description = "No imagestreams found."
                for isobj in iss[:15]:
                    meta = isobj.get("metadata", {})
                    status = isobj.get("status", {})
                    ns_name = meta.get("namespace", "?")
                    name = meta.get("name", "?")
                    tags = [t.get("tag") for t in (status.get("tags") or []) if t.get("tag")]
                    val = f"tags: {', '.join(tags)[:60]}" if tags else "no tags"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # OpenShift: BuildConfigs
            if resource in ["buildconfigs", "bc", "buildconfig"]:
                title_ns = (ns or "default") if not all_ns else None
                try:
                    if all_ns:
                        bcs = custom_objects.list_cluster_custom_object("build.openshift.io", "v1", "buildconfigs", label_selector=selector or None).get("items", [])
                    else:
                        bcs = custom_objects.list_namespaced_custom_object("build.openshift.io", "v1", title_ns, "buildconfigs", label_selector=selector or None).get("items", [])
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ BuildConfigs not available: {ae}", ephemeral=True)
                    return
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ BuildConfigs in `{title}`", color=discord.Color.dark_gold())
                if not bcs:
                    embed.description = "No buildconfigs found."
                for bc in bcs[:15]:
                    meta = bc.get("metadata", {})
                    spec = bc.get("spec", {})
                    status = bc.get("status", {})
                    ns_name = meta.get("namespace", "?")
                    name = meta.get("name", "?")
                    strategy = (spec.get("strategy") or {}).get("type", "?")
                    last = status.get("lastVersion", 0)
                    val = f"strategy: {strategy} • lastVersion: {last}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            # OpenShift: Builds
            if resource in ["builds", "build"]:
                title_ns = (ns or "default") if not all_ns else None
                try:
                    if all_ns:
                        builds = custom_objects.list_cluster_custom_object("build.openshift.io", "v1", "builds", label_selector=selector or None).get("items", [])
                    else:
                        builds = custom_objects.list_namespaced_custom_object("build.openshift.io", "v1", title_ns, "builds", label_selector=selector or None).get("items", [])
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ Builds not available: {ae}", ephemeral=True)
                    return
                title = title_ns or "all namespaces"
                embed = discord.Embed(title=f"☸️ Builds in `{title}`", color=discord.Color.dark_blue())
                if not builds:
                    embed.description = "No builds found."
                for b in builds[:15]:
                    meta = b.get("metadata", {})
                    status = b.get("status", {})
                    ns_name = meta.get("namespace", "?")
                    name = meta.get("name", "?")
                    phase = status.get("phase", "?")
                    bc_label = (meta.get("labels", {}) or {}).get("buildconfig") or (meta.get("labels", {}) or {}).get("openshift.io/build-config.name") or "-"
                    val = f"{phase} • bc: {bc_label}"
                    extra = f" ({ns_name})" if all_ns else ""
                    embed.add_field(name=name + extra, value=val, inline=False)
                await interaction.response.send_message(embed=embed)
                return

            await interaction.response.send_message(f"❌ Resource '{resource}' not supported yet.", ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Kubernetes API error: {ae}", ephemeral=True)

    async def _kubectl_describe(self, interaction: discord.Interaction, resource: str, name: str, ns: Optional[str]):
        resource = resource.lower()
        namespace = ns or "default"

        try:
            if resource in ["pod", "po", "pods"]:
                pod = v1.read_namespaced_pod(name=name, namespace=namespace)
                labels = getattr(getattr(pod, 'metadata', None), 'labels', None) or {}
                node = getattr(getattr(pod, 'spec', None), 'node_name', None) or "?"

                containers = getattr(getattr(pod, 'spec', None), 'containers', None) or []
                status = getattr(getattr(pod, 'status', None), 'phase', None) or "?"

                ips = getattr(getattr(pod, 'status', None), 'pod_ip', None) or "-"
                pod_name = getattr(getattr(pod, 'metadata', None), 'name', None) or name
                lines = [
                    f"Name: {pod_name}",
                    f"Namespace: {namespace}",
                    f"Node: {node}",
                    f"IP: {ips}",
                    f"Status: {status}",
                    f"Labels: {', '.join([f'{k}={v}' for k,v in labels.items()]) or '-'}",
                    "Containers:",
                ]
                for c in containers:
                    ports = ",".join([f"{p.container_port}/{p.protocol}" for p in (getattr(c, 'ports', None) or []) if getattr(p, 'container_port', None) is not None])
                    lines.append(f"  - {getattr(c, 'name', '?')}: {getattr(c, 'image', '?')} {ports}")
                text = "\n".join(lines)
                await interaction.response.send_message(f"```\n{self._truncate(text)}\n```", ephemeral=True)
                return

            if resource in ["route", "routes"]:
                try:
                    rt = custom_objects.get_namespaced_custom_object("route.openshift.io", "v1", namespace, "routes", name)
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ Failed to get Route: {ae}", ephemeral=True)
                    return
                meta = rt.get("metadata", {})
                spec = rt.get("spec", {})
                host = spec.get("host", "-")
                path = spec.get("path", "")
                to = spec.get("to", {})
                to_name = to.get("name", "?")
                tls = spec.get("tls", {})
                term = tls.get("termination", "")
                lines = [
                    f"Name: {meta.get('name', name)}",
                    f"Namespace: {namespace}",
                    f"Host: {host}{path or ''}",
                    f"To: {to_name}",
                    f"TLS: {term or '-'}",
                ]
                text = "\n".join(lines)
                await interaction.response.send_message(f"```\n{self._truncate(text)}\n```", ephemeral=True)
                return

            if resource in ["deploymentconfig", "deploymentconfigs", "dc"]:
                try:
                    dc = custom_objects.get_namespaced_custom_object("apps.openshift.io", "v1", namespace, "deploymentconfigs", name)
                except ApiException as ae:
                    await interaction.response.send_message(f"❌ Failed to get DeploymentConfig: {ae}", ephemeral=True)
                    return
                meta = dc.get("metadata", {})
                spec = dc.get("spec", {})
                status = dc.get("status", {})
                replicas = spec.get("replicas", 0)
                ready = status.get("availableReplicas", 0)
                selector = (spec.get("selector") or {})
                triggers = ",".join([t.get("type", "?") for t in (spec.get("triggers") or [])])
                lines = [
                    f"Name: {meta.get('name', name)}",
                    f"Namespace: {namespace}",
                    f"Replicas: {ready}/{replicas}",
                    f"Selector: {', '.join([f'{k}={v}' for k,v in selector.items()]) or '-'}",
                    f"Triggers: {triggers or '-'}",
                ]
                text = "\n".join(lines)
                await interaction.response.send_message(f"```\n{self._truncate(text)}\n```", ephemeral=True)
                return

            if resource in ["deployment", "deploy", "deployments"]:
                dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                labels = getattr(getattr(dep, 'metadata', None), 'labels', None) or {}
                selector = getattr(getattr(getattr(dep, 'spec', None), 'selector', None), 'match_labels', None) or {}
                replicas = getattr(getattr(dep, 'spec', None), 'replicas', None) or 0
                ready = getattr(getattr(dep, 'status', None), 'ready_replicas', None) or 0
                tmpl_spec = getattr(getattr(getattr(dep, 'spec', None), 'template', None), 'spec', None)
                containers = getattr(tmpl_spec, 'containers', None) or []
                dep_name = getattr(getattr(dep, 'metadata', None), 'name', None) or name
                lines = [
                    f"Name: {dep_name}",
                    f"Namespace: {namespace}",
                    f"Replicas: {ready}/{replicas}",
                    f"Labels: {', '.join([f'{k}={v}' for k,v in labels.items()]) or '-'}",
                    f"Selector: {', '.join([f'{k}={v}' for k,v in selector.items()]) or '-'}",
                    "Containers:",
                ]
                for c in containers:
                    envs = ",".join([e.name for e in (getattr(c, 'env', None) or []) if getattr(e, 'name', None)])
                    lines.append(f"  - {getattr(c, 'name', '?')}: {getattr(c, 'image', '?')} env[{envs}]")
                text = "\n".join(lines)
                await interaction.response.send_message(f"```\n{self._truncate(text)}\n```", ephemeral=True)
                return

            if resource in ["service", "svc", "services"]:
                svc = v1.read_namespaced_service(name=name, namespace=namespace)
                stype = getattr(getattr(svc, 'spec', None), 'type', None) or '?'
                selector = getattr(getattr(svc, 'spec', None), 'selector', None) or {}
                ports = getattr(getattr(svc, 'spec', None), 'ports', None) or []
                cluster_ip = getattr(getattr(svc, 'spec', None), 'cluster_ip', None) or '?'
                lines = [
                    f"Name: {getattr(getattr(svc, 'metadata', None), 'name', None) or name}",
                    f"Namespace: {namespace}",
                    f"Type: {stype}",
                    f"Cluster IP: {cluster_ip}",
                    f"Selector: {', '.join([f'{k}={v}' for k,v in selector.items()]) or '-'}",
                    "Ports:",
                ]
                for p in ports:
                    lines.append(f"  - {getattr(p, 'port', '?')}/{getattr(p, 'protocol', '?')} -> {getattr(p, 'target_port', '?')}")
                text = "\n".join(lines)
                await interaction.response.send_message(f"```\n{self._truncate(text)}\n```", ephemeral=True)
                return

            if resource in ["node", "nodes", "no"]:
                node = v1.read_node(name=name)
                labels = getattr(getattr(node, 'metadata', None), 'labels', None) or {}
                capacity = getattr(getattr(node, 'status', None), 'capacity', None) or {}
                alloc = getattr(getattr(node, 'status', None), 'allocatable', None) or {}
                addresses = getattr(getattr(node, 'status', None), 'addresses', None) or []
                addr_str = ", ".join([f"{getattr(a,'type','')}: {getattr(a,'address','')}" for a in addresses])
                node_name = getattr(getattr(node, 'metadata', None), 'name', None) or name
                lines = [
                    f"Name: {node_name}",
                    f"Labels: {', '.join([f'{k}={v}' for k,v in labels.items()]) or '-'}",
                    f"Capacity: {capacity}",
                    f"Allocatable: {alloc}",
                    f"Addresses: {addr_str}",
                ]
                text = "\n".join(lines)
                await interaction.response.send_message(f"```\n{self._truncate(text)}\n```", ephemeral=True)
                return

            await interaction.response.send_message(f"❌ 'describe' for resource '{resource}' not supported.", ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Kubernetes API error: {ae}", ephemeral=True)

    async def _kubectl_logs(self, interaction: discord.Interaction, pod: str, namespace: str, container: Optional[str], tail_lines: int, since_seconds: Optional[int], previous: bool):
        try:
            log = v1.read_namespaced_pod_log(
                name=pod,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
                timestamps=True,
                since_seconds=since_seconds,
                previous=previous,
            )
            text = self._truncate(log, MAX_MESSAGE_LEN)
            if len(text) < 1800:
                await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)
            else:
                data = io.BytesIO(text.encode("utf-8"))
                await interaction.response.send_message(content=f"Logs for {pod} ({namespace})", file=discord.File(data, filename=f"{pod}.log.txt"), ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Failed to get logs: {ae}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to get logs: {e}", ephemeral=True)

    async def _kubectl_scale_deployment(self, interaction: discord.Interaction, name: str, namespace: str, replicas: int):
        try:
            body = {"spec": {"replicas": replicas}}
            apps_v1.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
            await interaction.response.send_message(f"✅ Scaled deployment `{name}` to {replicas} replicas in `{namespace}`.", ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Failed to scale: {ae}", ephemeral=True)

    async def _kubectl_rollout_restart(self, interaction: discord.Interaction, name: str, namespace: str):
        try:
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {"kubectl.kubernetes.io/restartedAt": now}
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
            await interaction.response.send_message(f"🔁 Rollout restart triggered for deployment `{name}` in `{namespace}`.", ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Failed to rollout restart: {ae}", ephemeral=True)

    async def _oc_rollout_restart_dc(self, interaction: discord.Interaction, name: str, namespace: str):
        try:
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {"openshift.io/restartedAt": now}
                        }
                    }
                }
            }
            custom_objects.patch_namespaced_custom_object(
                group="apps.openshift.io", version="v1", namespace=namespace, plural="deploymentconfigs", name=name, body=body
            )
            await interaction.response.send_message(f"🔁 Rollout restart triggered for deploymentconfig `{name}` in `{namespace}`.", ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Failed to rollout restart DC: {ae}", ephemeral=True)

    async def _kubectl_top(self, interaction: discord.Interaction, what: str, namespace: str):
        try:
            what = what.lower()
            if what in ["pods", "po"]:
                data = custom_objects.list_namespaced_custom_object(group="metrics.k8s.io", version="v1beta1", namespace=namespace, plural="pods")
                items = data.get("items", [])
                embed = discord.Embed(title=f"☸️ Top Pods in `{namespace}`", color=discord.Color.dark_green())
                lines = []
                for it in items:
                    meta = it.get("metadata", {})
                    pod_name = meta.get("name", "?")
                    containers = it.get("containers", [])
                    cpu_m = 0
                    mem_mi = 0
                    for c in containers:
                        cpu = c.get("usage", {}).get("cpu", "0")
                        mem = c.get("usage", {}).get("memory", "0")
                        if cpu.endswith('m'):
                            cpu_m += int(cpu[:-1])
                        else:
                            try:
                                cpu_m += int(float(cpu) * 1000)
                            except Exception:
                                pass
                        if mem.endswith('Ki'):
                            mem_mi += int(int(mem[:-2]) / 1024)
                        elif mem.endswith('Mi'):
                            mem_mi += int(mem[:-2])
                        elif mem.endswith('Gi'):
                            mem_mi += int(mem[:-2]) * 1024
                    lines.append((pod_name, cpu_m, mem_mi))
                lines.sort(key=lambda x: (x[1], x[2]), reverse=True)
                for name, cpu, mem in lines[:15]:
                    embed.add_field(name=name, value=f"CPU: {cpu}m • MEM: {mem}Mi", inline=False)
                await interaction.response.send_message(embed=embed)
                return
            if what in ["nodes", "no"]:
                data = custom_objects.list_cluster_custom_object(group="metrics.k8s.io", version="v1beta1", plural="nodes")
                items = data.get("items", [])
                embed = discord.Embed(title="☸️ Top Nodes", color=discord.Color.dark_green())
                lines = []
                for it in items:
                    meta = it.get("metadata", {})
                    node_name = meta.get("name", "?")
                    usage = it.get("usage", {})
                    cpu = usage.get("cpu", "0")
                    mem = usage.get("memory", "0")
                    cpu_m = int(cpu[:-1]) if cpu.endswith('m') else int(float(cpu) * 1000) if cpu else 0
                    if mem.endswith('Ki'):
                        mem_mi = int(int(mem[:-2]) / 1024)
                    elif mem.endswith('Mi'):
                        mem_mi = int(mem[:-2])
                    elif mem.endswith('Gi'):
                        mem_mi = int(mem[:-2]) * 1024
                    else:
                        mem_mi = 0
                    lines.append((node_name, cpu_m, mem_mi))
                lines.sort(key=lambda x: (x[1], x[2]), reverse=True)
                for name, cpu, mem in lines[:15]:
                    embed.add_field(name=name, value=f"CPU: {cpu}m • MEM: {mem}Mi", inline=False)
                await interaction.response.send_message(embed=embed)
                return
            await interaction.response.send_message("❌ Usage: top <pods|nodes>", ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ Metrics API error: {ae}", ephemeral=True)
        except Exception:
            await interaction.response.send_message("⚠️ Metrics not available (is metrics-server installed?)", ephemeral=True)

    async def _oc_whoami(self, interaction: discord.Interaction):
        try:
            user = custom_objects.get_cluster_custom_object("user.openshift.io", "v1", "users", "~")
            meta = user.get("metadata", {})
            name = user.get("metadata", {}).get("name") or user.get("fullName") or user.get("name") or "?"
            uid = meta.get("uid", "?")
            groups = user.get("groups") or []
            embed = discord.Embed(title="☸️ OpenShift WhoAmI", color=discord.Color.blurple())
            embed.add_field(name="User", value=name, inline=False)
            embed.add_field(name="UID", value=uid, inline=False)
            if groups:
                embed.add_field(name="Groups", value=", ".join(groups)[:950], inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ApiException as ae:
            await interaction.response.send_message(f"❌ whoami not available: {ae}", ephemeral=True)
async def setup(bot: commands.Bot):
    await bot.add_cog(KubernetesCog(bot))