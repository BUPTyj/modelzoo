# Copyright (c) 2018, deepakn94, codyaustun, robieta. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# -----------------------------------------------------------------------
#
# Copyright (c) 2018, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from argparse import ArgumentParser
import pandas as pd
from load import implicit_load
import torch
import torch_sdaa

from mlperf_compliance import mlperf_log

MIN_RATINGS = 20
USER_COLUMN = 'user_id'
ITEM_COLUMN = 'item_id'

def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--path', type=str, default='/data/ml-20m/ratings.csv',
                        help='Path to ratings.csv file from MovieLens')
    parser.add_argument('--output', type=str, default='/data',
                        help='Output directory for train and test files')
    return parser.parse_args()

def main():
    args = parse_args()

    print("Loading raw data from {}".format(args.path))
    df = implicit_load(args.path, sort=False)

    print("Filtering out users with less than {} ratings".format(MIN_RATINGS))
    grouped = df.groupby(USER_COLUMN)
    mlperf_log.ncf_print(key=mlperf_log.PREPROC_HP_MIN_RATINGS, value=MIN_RATINGS)
    df = grouped.filter(lambda x: len(x) >= MIN_RATINGS)

    print("Mapping original user and item IDs to new sequential IDs")
    df[USER_COLUMN] = pd.factorize(df[USER_COLUMN])[0]
    df[ITEM_COLUMN] = pd.factorize(df[ITEM_COLUMN])[0]

    print("Creating list of items for each user")
    # Need to sort before popping to get last item
    df.sort_values(by='timestamp', inplace=True)

    # clean up data
    del df['rating'], df['timestamp']
    df = df.drop_duplicates() # assuming it keeps order

    # now we have filtered and sorted by time data, we can split test data out
    grouped_sorted = df.groupby(USER_COLUMN, group_keys=False)
    test_data = grouped_sorted.tail(1).sort_values(by='user_id')
    # need to pop for each group
    train_data = grouped_sorted.apply(lambda x: x.iloc[:-1])

    # Note: no way to keep reference training data ordering because use of python set and multi-process
    # It should not matter since it will be later randomized again
    # save train and val data that is fixed.
    train_ratings = torch.from_numpy(train_data.values)
    torch.save(train_ratings, args.output+'/train_ratings.pt')
    test_ratings = torch.from_numpy(test_data.values)
    torch.save(test_ratings, args.output+'/test_ratings.pt')

if __name__ == '__main__':
    main()
