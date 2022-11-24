#
# Copyright (c) 2022, salesforce.com, inc.
#  All rights reserved.
#  SPDX-License-Identifier: BSD-3-Clause
#  For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
#

# create database botsim
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/botsim
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/botsim_s3
heroku pg:psql postgresql-vertical-54506 --app salesforce-botsim
