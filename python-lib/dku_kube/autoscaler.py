import os, json, logging
from .kubectl_command import run_with_timeout
from dku_utils.access import _is_none_or_blank
from dku_utils.tools_version import get_kubernetes_default_version

AUTOSCALER_IMAGES = {
    '1.20': 'k8s.gcr.io/autoscaling/cluster-autoscaler:v1.20.3',
    '1.21': 'k8s.gcr.io/autoscaling/cluster-autoscaler:v1.21.2',
    '1.22': 'k8s.gcr.io/autoscaling/cluster-autoscaler:v1.22.2',
    '1.23': 'k8s.gcr.io/autoscaling/cluster-autoscaler:v1.23.1',
    '1.24': 'registry.k8s.io/autoscaling/cluster-autoscaler:v1.24.3',
    '1.25': 'registry.k8s.io/autoscaling/cluster-autoscaler:v1.25.3',
    '1.26': 'registry.k8s.io/autoscaling/cluster-autoscaler:v1.26.4',
    '1.27': 'registry.k8s.io/autoscaling/cluster-autoscaler:v1.27.3',
    '1.28': 'registry.k8s.io/autoscaling/cluster-autoscaler:v1.28.0'
}

def has_autoscaler(kube_config_path):
    env = os.environ.copy()
    env['KUBECONFIG'] = kube_config_path
    cmd = ['kubectl', 'get', 'pods', '--namespace', 'kube-system', '-l', 'app=cluster-autoscaler', '--ignore-not-found']
    logging.info("Checking autoscaler presence with : %s" % json.dumps(cmd))
    out, err = run_with_timeout(cmd, env=env, timeout=5)
    return len(out.strip()) > 0

def add_autoscaler_if_needed(cluster_id, cluster_config, kube_config_path, kubernetes_version):
    if not has_autoscaler(kube_config_path):
        if _is_none_or_blank(kubernetes_version):
            kubernetes_version = get_kubernetes_default_version(cluster_config)
        autoscaler_file_path = 'autoscaler.yaml'
        if float(kubernetes_version) < 1.20:
          autoscaler_image = AUTOSCALER_IMAGES.get('1.20', 'k8s.gcr.io/autoscaling/cluster-autoscaler:v1.20.3')
        else:  
          autoscaler_image = AUTOSCALER_IMAGES.get(kubernetes_version, 'registry.k8s.io/autoscaling/cluster-autoscaler:v1.28.0')
        with open(autoscaler_file_path, 'w') as f:
            f.write(get_autoscaler_def(cluster_id, autoscaler_image))
        cmd = ['kubectl', 'create', '-f', os.path.abspath(autoscaler_file_path)]
        logging.info("Create autoscaler with : %s" % json.dumps(cmd))
        env = os.environ.copy()
        env['KUBECONFIG'] = kube_config_path
        run_with_timeout(cmd, env=env, timeout=5)
        
def get_autoscaler_def(cluster_id, autoscaler_image):
    # the auto-discovery version from https://github.com/kubernetes/autoscaler/tree/master/cluster-autoscaler/cloudprovider/aws
    # all the necessary roles and tags are handled by eksctl with the --asg-access flag
    yaml = """
---
apiVersion: v1
kind: ServiceAccount
metadata:
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
  name: cluster-autoscaler
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cluster-autoscaler
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
rules:
  - apiGroups: [""]
    resources: ["events", "endpoints"]
    verbs: ["create", "patch"]
  - apiGroups: [""]
    resources: ["pods/eviction"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods/status"]
    verbs: ["update"]
  - apiGroups: [""]
    resources: ["endpoints"]
    resourceNames: ["cluster-autoscaler"]
    verbs: ["get", "update"]
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["watch", "list", "get", "update"]
  - apiGroups: [""]
    resources:
      - "namespaces"
      - "pods"
      - "services"
      - "replicationcontrollers"
      - "persistentvolumeclaims"
      - "persistentvolumes"
    verbs: ["watch", "list", "get"]
  - apiGroups: ["extensions"]
    resources: ["replicasets", "daemonsets"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["watch", "list"]
  - apiGroups: ["apps"]
    resources: ["statefulsets", "replicasets", "daemonsets"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses", "csinodes", "csidrivers", "csistoragecapacities"]
    verbs: ["watch", "list", "get"]
  - apiGroups: ["batch", "extensions"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch", "patch"]
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["create"]
  - apiGroups: ["coordination.k8s.io"]
    resourceNames: ["cluster-autoscaler"]
    resources: ["leases"]
    verbs: ["get", "update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cluster-autoscaler
  namespace: kube-system
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["create","list","watch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["cluster-autoscaler-status", "cluster-autoscaler-priority-expander"]
    verbs: ["delete", "get", "update", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cluster-autoscaler
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-autoscaler
subjects:
  - kind: ServiceAccount
    name: cluster-autoscaler
    namespace: kube-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cluster-autoscaler
  namespace: kube-system
  labels:
    k8s-addon: cluster-autoscaler.addons.k8s.io
    k8s-app: cluster-autoscaler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: cluster-autoscaler
subjects:
  - kind: ServiceAccount
    name: cluster-autoscaler
    namespace: kube-system

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-autoscaler
  namespace: kube-system
  labels:
    app: cluster-autoscaler
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cluster-autoscaler
  template:
    metadata:
      labels:
        app: cluster-autoscaler
    spec:
      serviceAccountName: cluster-autoscaler
      containers:
        - image: %(autoscalerimage)s
          name: cluster-autoscaler
          resources:
            limits:
              cpu: 100m
              memory: 600Mi
            requests:
              cpu: 100m
              memory: 600Mi
          command:
            - ./cluster-autoscaler
            - --v=4
            - --stderrthreshold=info
            - --cloud-provider=aws
            - --skip-nodes-with-local-storage=false
            - --expander=least-waste
            - --node-group-auto-discovery=asg:tag=k8s.io/cluster-autoscaler/enabled,k8s.io/cluster-autoscaler/%(clusterid)s
          volumeMounts:
            - name: ssl-certs
              mountPath: /etc/ssl/certs/ca-certificates.crt #/etc/ssl/certs/ca-bundle.crt for Amazon Linux Worker Nodes
              readOnly: true
          imagePullPolicy: "Always"
      volumes:
        - name: ssl-certs
          hostPath:
            path: "/etc/ssl/certs/ca-bundle.crt"
""" % {'autoscalerimage': autoscaler_image, 'clusterid': cluster_id}
    return yaml