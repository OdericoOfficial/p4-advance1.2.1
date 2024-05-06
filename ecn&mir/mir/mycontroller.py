#!/usr/bin/env python3
import argparse
import os
import sys
from time import sleep
import grpc


sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections


# 定义进行ipv4报文转发的流表项
def writeIpForwardRules(p4info_helper, ingress_sw, egress_sw, mfs, myd, mp):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": mfs
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr": myd,
            "port": mp
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed transit ipforward rule on %s" % ingress_sw.name)


# 定义动态下发交换机id的流表项
def writeSwitchId(p4info_helper, ingress_sw, egress_sw, action_params):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyEgress.swtrace",
        default_action=True,
        action_name="MyEgress.add_swtrace",
        action_params=action_params
    )
    ingress_sw.WriteTableEntry(table_entry)


def main(p4info_file_path, bmv2_file_path):
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:

        s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s1',
            address='127.0.0.1:50051',
            device_id=0,
            proto_dump_file='logs/s1-p4runtime-requests.txt')
        s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s2',
            address='127.0.0.1:50052',
            device_id=1,
            proto_dump_file='logs/s2-p4runtime-requests.txt')
        s3 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s3',
            address='127.0.0.1:50053',
            device_id=2,
            proto_dump_file='logs/s3-p4runtime-requests.txt')

        s1.MasterArbitrationUpdate()
        s2.MasterArbitrationUpdate()
        s3.MasterArbitrationUpdate()

        s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s1")
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s2")
        s3.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s3")

        writeIpForwardRules(p4info_helper, ingress_sw=s1, egress_sw=s1, mfs=["10.0.1.1", 32],
                            myd="08:00:00:00:01:01", mp=2)
        writeIpForwardRules(p4info_helper, ingress_sw=s1, egress_sw=s1, mfs=["10.0.1.11", 32],
                            myd="08:00:00:00:01:11", mp=1)
        writeIpForwardRules(p4info_helper, ingress_sw=s1, egress_sw=s2, mfs=["10.0.2.0", 24],
                            myd="08:00:00:00:02:00", mp=3)
        writeIpForwardRules(p4info_helper, ingress_sw=s1, egress_sw=s3, mfs=["10.0.3.0", 24],
                            myd="08:00:00:00:03:00", mp=4)

        # s2的流规则
        writeIpForwardRules(p4info_helper, ingress_sw=s2, egress_sw=s2, mfs=["10.0.2.2", 32],
                            myd="08:00:00:00:02:02", mp=2)
        writeIpForwardRules(p4info_helper, ingress_sw=s2, egress_sw=s2, mfs=["10.0.2.22", 32],
                            myd="08:00:00:00:02:22", mp=1)
        writeIpForwardRules(p4info_helper, ingress_sw=s2, egress_sw=s1, mfs=["10.0.1.0", 24],
                            myd="08:00:00:00:01:00", mp=3)
        writeIpForwardRules(p4info_helper, ingress_sw=s2, egress_sw=s3, mfs=["10.0.3.0", 24],
                            myd="08:00:00:00:03:00", mp=4)

        # s3的流规则
        writeIpForwardRules(p4info_helper, ingress_sw=s3, egress_sw=s3, mfs=["10.0.3.3", 32],
                            myd="08:00:00:00:03:03", mp=1)
        writeIpForwardRules(p4info_helper, ingress_sw=s3, egress_sw=s1, mfs=["10.0.1.0", 24],
                            myd="08:00:00:00:01:00", mp=2)
        writeIpForwardRules(p4info_helper, ingress_sw=s3, egress_sw=s2, mfs=["10.0.2.0", 24],
                            myd="08:00:00:00:02:00", mp=3)

        # 交换机id的动态下发
        writeSwitchId(p4info_helper, s1, s1, {"swid": 1})
        writeSwitchId(p4info_helper, s2, s2, {"swid": 2})
        writeSwitchId(p4info_helper, s3, s3, {"swid": 3})

    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)

    ShutdownAllSwitchConnections()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/mri.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/mri.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found: %s\nHave you run 'make'?" % args.p4info)
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json)
        parser.exit(1)
    main(args.p4info, args.bmv2_json)
