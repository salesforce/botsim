#
# Copyright (c) 2022, salesforce.com, inc.
#  All rights reserved.
#  SPDX-License-Identifier: BSD-3-Clause
#  For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
#

gcloud container clusters get-credentials sfr-demo-232-us-central1-a --zone us-central1-a --project salesforce-research-internal
kubens sfr-ns-guangsen-wang
TAG="gcr.io/salesforce-research-internal/botsim_streamlit_heroku_gpu"
gcloud builds submit . -t=$TAG --machine-type=n1-highcpu-32 --timeout=9000
kubectl apply -n sfr-ns-guangsen-wang -f botsim/deployments/docker/deploy_gpu_service_streamlit_heroku.yaml
kubectl -n sfr-ns-guangsen-wang get pods
# get ip addresses
kubectl -n sfr-ns-guangsen-wang get services

