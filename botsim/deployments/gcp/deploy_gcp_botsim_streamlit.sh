#
# Copyright (c) 2022, salesforce.com, inc.
#  All rights reserved.
#  SPDX-License-Identifier: BSD-3-Clause
#  For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
#

# authentication required for gcp
gcloud container clusters get-credentials $cluster_name --zone us-central1-a --project $project_name
kubens $user_name_space

# create gcp image
TAG="gcr.io/${project_name}/botsim_streamlit_gpu"
gcloud builds submit . -t=$TAG --machine-type=n1-highcpu-32 --timeout=9000

# deploy to gcp
kubectl apply -n $user_name_space -f deploy_gpu_streamlit_botsim.yaml
kubectl -n $user_name_space get pods
kubectl -n $user_name_space get services

