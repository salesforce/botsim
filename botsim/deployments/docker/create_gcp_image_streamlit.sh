#
# Copyright (c) 2022, salesforce.com, inc.
#  All rights reserved.
#  SPDX-License-Identifier: BSD-3-Clause
#  For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
#

gcloud container clusters get-credentials sfr-prem1-234-us-central1 --zone us-central1 --project salesforce-research-internal
gcloud config set project "salesforce-research-internal"
#git pull
TAG="gcr.io/salesforce-research-internal/botsim_streamlit_heroku_cpu"
gcloud builds submit . -t=$TAG --machine-type=n1-highcpu-32 --timeout=900

kubectl apply -n sfr-ns-guangsen-wang -f botsim/deployments/docker/deploy_service_streamlit_heroku.yaml

kubectl -n sfr-ns-guangsen-wang get pods
# get ip addresses
kubectl -n sfr-ns-guangsen-wang get services

